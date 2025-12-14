"""Helpers for interacting with the Firefly III API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, cast

from requests.exceptions import HTTPError, RequestException

import requests
from firefly_preimporter.models import FireflyPayload, UploadedGroup

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from pathlib import Path

    from firefly_preimporter.config import FireflySettings
    from requests import Session


class FireflyEmitter(Protocol):
    def __call__(self, message: str, *, error: bool = False, verbose_only: bool = False) -> None: ...


def _mask_account_number(account_number: str) -> str:
    """Return a masked representation that only reveals the last four characters."""

    clean = account_number.strip()
    if len(clean) <= 4:
        return clean
    masked_prefix = '*' * (len(clean) - 4)
    return f'{masked_prefix}{clean[-4:]}'


def _format_firefly_status(payload: FireflyPayload) -> str:
    transactions = payload.transactions
    split = transactions[0] if transactions else None
    date = split.date if split and split.date else '?'
    description_full = (split.description if split and split.description else '').replace('\n', ' ').strip()
    truncated = description_full[:20]
    if len(description_full) > len(truncated):
        truncated = f'{truncated}\u2026'
    description = truncated
    return f'{date} "{description}"'.strip()


def _emit_response_snippet(
    emit: FireflyEmitter,
    body_text: str,
    *,
    error: bool = False,
    verbose_only: bool = False,
) -> None:
    snippet = body_text.strip()
    if len(snippet) > 500:
        snippet = f'{snippet[:500]}…'
    if not snippet:
        snippet = '<empty response body>'
    emit(f'Firefly response body: {snippet}', error=error, verbose_only=verbose_only)


def _emit_upload_error(emit: FireflyEmitter, exc: Exception) -> None:
    emit(f'Error uploading payload to Firefly III: {exc}', error=True)


def _is_duplicate_error(response: requests.Response | None) -> bool:
    if response is None:
        return False
    text = getattr(response, 'text', '') or ''
    return 'duplicate of transaction' in text.lower()


def _verify_option(settings: FireflySettings) -> bool | str:
    if settings.ca_cert_path and settings.ca_cert_path.exists():
        return str(settings.ca_cert_path)
    return True


def fetch_asset_accounts(
    settings: FireflySettings,
    *,
    session: Session | None = None,
) -> list[dict[str, object]]:
    """Return the list of asset accounts available to the configured user."""

    http = session or requests.Session()
    base_url = settings.firefly_api_base.rstrip('/')
    url: str | None = f'{base_url}/accounts'
    params: dict[str, str] | None = {'type': 'asset', 'limit': '50', 'page': '1'}
    headers = {
        'Authorization': f'Bearer {settings.personal_access_token}',
        'Accept': 'application/json',
    }
    accounts: list[dict[str, object]] = []

    while url:
        response = http.get(
            url,
            headers=headers,
            params=params,
            timeout=settings.request_timeout,
            verify=_verify_option(settings),
        )
        response.raise_for_status()
        payload = cast('dict[str, Any]', response.json())
        raw_data = payload.get('data', [])
        if isinstance(raw_data, list):
            entries = [entry for entry in raw_data if isinstance(entry, dict)]
            accounts.extend(cast('list[dict[str, object]]', entries))
        links = payload.get('links', {})
        if isinstance(links, Mapping):
            next_url = links.get('next')
            url = str(next_url) if isinstance(next_url, str) and next_url else None
        else:
            url = None
        params = None

    if not accounts:
        raise ValueError('No asset accounts returned from Firefly III.')

    return accounts


def format_account_label(account: Mapping[str, Any]) -> str:
    """Return a friendly label describing ``account`` for CLI prompts."""

    attributes = account.get('attributes', {})
    if isinstance(attributes, Mapping):
        name = str(attributes.get('name') or '').strip()
        acct_number = str(attributes.get('account_number') or '').strip()
    else:  # pragma: no cover - defensive fallback
        name = ''
        acct_number = ''
    label = name or f'Account {account.get("id", "?")}'
    if acct_number:
        masked = _mask_account_number(acct_number)
        label = f'{label} (#{masked})'
    return label


def _extract_uploaded_groups(response: requests.Response) -> list[UploadedGroup]:
    """Return Firefly transaction group metadata from ``response``."""

    try:
        payload = response.json()
    except ValueError:
        return []
    data = payload.get('data')
    entries: list[Mapping[str, Any]] = []
    if isinstance(data, list):
        entries = [entry for entry in data if isinstance(entry, Mapping)]
    elif isinstance(data, Mapping):
        entries = [data]
    else:
        return []
    groups: list[UploadedGroup] = []
    for entry in entries:
        group_id = entry.get('id')
        try:
            group_id_int = int(str(group_id))
        except (TypeError, ValueError):
            continue
        attributes = entry.get('attributes')
        transactions = attributes.get('transactions') if isinstance(attributes, Mapping) else None
        if not isinstance(transactions, list):
            continue
        journals: dict[int, list[str]] = {}
        for txn in transactions:
            if not isinstance(txn, Mapping):
                continue
            journal_id = txn.get('transaction_journal_id') or txn.get('id')
            try:
                journal_id_int = int(str(journal_id))
            except (TypeError, ValueError):
                continue
            tags_raw = txn.get('tags', [])
            tags: list[str] = []
            if isinstance(tags_raw, list):
                tags = [str(tag) for tag in tags_raw if isinstance(tag, str) and tag]
            journals[journal_id_int] = tags
        if journals:
            groups.append(UploadedGroup(group_id=group_id_int, journals=journals))
    return groups


def _merge_tags(existing: list[str], new_tag: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for tag in [*existing, new_tag]:
        if not tag or tag in seen:
            continue
        ordered.append(tag)
        seen.add(tag)
    return ordered


def _ensure_tag_exists(settings: FireflySettings, tag: str) -> None:
    base_url = settings.firefly_api_base.rstrip('/')
    url = f'{base_url}/tags'
    body = {'tag': tag, 'date': datetime.now().date().isoformat()}
    response = requests.post(  # type: ignore[attr-defined]
        url,
        headers={
            'Authorization': f'Bearer {settings.personal_access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        json=body,
        timeout=settings.request_timeout,
        verify=_verify_option(settings),
    )
    try:
        response.raise_for_status()
    except HTTPError as exc:
        resp = exc.response
        # Tag already exists -> Firefly returns 422. Treat as success.
        if resp is not None and getattr(resp, 'status_code', None) == 422:
            return
        raise


def _append_tag_to_group(
    settings: FireflySettings,
    group_id: int,
    journal_map: Mapping[int, list[str]],
    *,
    tag: str,
) -> requests.Response:
    base_url = settings.firefly_api_base.rstrip('/')
    url = f'{base_url}/transactions/{group_id}'
    transactions_payload: list[dict[str, object]] = []
    for journal_id, tags in journal_map.items():
        merged_tags = _merge_tags(list(tags), tag)
        transactions_payload.append({'transaction_journal_id': str(journal_id), 'tags': merged_tags})
    response = requests.put(  # type: ignore[attr-defined]
        url,
        headers={
            'Authorization': f'Bearer {settings.personal_access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        json={'transactions': transactions_payload},
        timeout=settings.request_timeout,
        verify=_verify_option(settings),
    )
    response.raise_for_status()
    return response


def _apply_batch_tag(
    settings: FireflySettings,
    *,
    tag: str,
    groups: list[UploadedGroup],
    emit: FireflyEmitter,
) -> None:
    try:
        _ensure_tag_exists(settings, tag)
    except HTTPError as exc:
        _emit_upload_error(emit, exc)
        if exc.response is not None:
            _emit_response_snippet(emit, getattr(exc.response, 'text', '') or '', error=True)
        raise
    except Exception as exc:
        _emit_upload_error(emit, exc)
        raise
    for group in groups:
        journal_map = group.journals
        if not journal_map:
            continue
        response = _append_tag_to_group(settings, group.group_id, journal_map, tag=tag)
        _emit_response_snippet(emit, getattr(response, 'text', '') or '', verbose_only=True)


def write_firefly_payloads(payloads: list[FireflyPayload], output_path: Path, *, emit: FireflyEmitter) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = [payload.to_dict() for payload in payloads]
    output_path.write_text(json.dumps(serialized, indent=2), encoding='utf-8')
    emit(f'Wrote Firefly API payloads to {output_path}')


def upload_transactions(
    settings: FireflySettings,
    payload: FireflyPayload,
    *,
    session: Session | None = None,
) -> requests.Response:
    """POST ``payload`` to the Firefly III transactions endpoint."""

    http = session or requests.Session()
    base_url = settings.firefly_api_base.rstrip('/')
    url = f'{base_url}/transactions'
    payload_dict = payload.to_dict()
    headers = {
        'Authorization': f'Bearer {settings.personal_access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = http.post(
        url,
        headers=headers,
        json=payload_dict,
        timeout=settings.request_timeout,
        verify=_verify_option(settings),
    )
    response.raise_for_status()
    return response


def upload_firefly_payloads(
    payloads: list[FireflyPayload],
    settings: FireflySettings,
    *,
    emit: FireflyEmitter,
    batch_tag: str | None = None,
) -> int:
    uploaded_groups: list[UploadedGroup] = []
    for payload in payloads:
        status_label = _format_firefly_status(payload)
        try:
            response = upload_transactions(settings, payload)
        except HTTPError as exc:
            response = cast('requests.Response | None', exc.response)
            if _is_duplicate_error(response):
                emit(f'Firefly upload {status_label} - duplicate')
                if response is not None:
                    body_text = getattr(response, 'text', '') or ''
                    _emit_response_snippet(emit, body_text, verbose_only=True)
                continue
            emit(f'Firefly upload {status_label} - failed', error=True)
            _emit_upload_error(emit, exc)
            if response is not None:
                body_text = getattr(response, 'text', '') or ''
                _emit_response_snippet(emit, body_text, error=True)
            return 1
        except Exception as exc:  # noqa: BLE001 - defensive logging
            emit(f'Firefly upload {status_label} - failed', error=True)
            _emit_upload_error(emit, exc)
            return 1
        emit(f'Firefly upload {status_label} - done')
        body_text = getattr(response, 'text', '') or ''
        _emit_response_snippet(emit, body_text, verbose_only=True)
        uploaded_groups.extend(_extract_uploaded_groups(response))
    if batch_tag and uploaded_groups:
        try:
            _apply_batch_tag(settings, tag=batch_tag, groups=uploaded_groups, emit=emit)
        except RequestException as exc:
            _emit_upload_error(emit, exc)
            return 1
    return 0
