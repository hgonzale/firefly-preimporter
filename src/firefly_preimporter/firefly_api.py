"""Helpers for interacting with the Firefly III API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import requests

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from firefly_preimporter.config import FireflySettings
    from requests import Session


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
        label = f'{label} (#{acct_number})'
    return label


def upload_transactions(
    settings: FireflySettings,
    payload: Mapping[str, Any],
    *,
    session: Session | None = None,
) -> requests.Response:
    """POST ``payload`` to the Firefly III transactions endpoint."""

    http = session or requests.Session()
    base_url = settings.firefly_api_base.rstrip('/')
    url = f'{base_url}/transactions'
    headers = {
        'Authorization': f'Bearer {settings.personal_access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    response = http.post(
        url,
        headers=headers,
        json=payload,
        timeout=settings.request_timeout,
        verify=_verify_option(settings),
    )
    response.raise_for_status()
    return response
