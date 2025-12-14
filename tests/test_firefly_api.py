import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from requests.exceptions import HTTPError, RequestException

import firefly_preimporter.firefly_api as firefly_api
import requests
from firefly_preimporter.config import FireflySettings
from firefly_preimporter.firefly_api import (
    fetch_asset_accounts,
    format_account_label,
    upload_firefly_payloads,
    upload_transactions,
    write_firefly_payloads,
)
from firefly_preimporter.models import FireflyPayload, FireflyTransactionSplit, UploadedGroup
from requests import Response


def _settings() -> FireflySettings:
    return FireflySettings(
        fidi_import_secret='sec',  # noqa: S106 - mock secret for tests
        personal_access_token='token',  # noqa: S106 - mock token for tests
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://firefly.example/api/v1',
        ca_cert_path=None,
        request_timeout=5,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={},
        firefly_error_on_duplicate=True,
    )


def _make_split() -> FireflyTransactionSplit:
    return FireflyTransactionSplit(
        type='withdrawal',
        date='2025-01-01',
        amount='10',
        currency_code='USD',
        description='Coffee',
        external_id='abc',
        notes='Coffee',
        error_if_duplicate_hash=True,
        internal_reference='abc',
        source_id=1,
    )


def _make_payload(transactions: list[FireflyTransactionSplit] | None = None) -> FireflyPayload:
    return FireflyPayload(
        group_title='firefly-preimporter',
        error_if_duplicate_hash=True,
        apply_rules=True,
        fire_webhooks=True,
        transactions=transactions or [_make_split()],
    )


def test_fetch_asset_accounts_handles_pagination() -> None:
    session = Mock(spec=requests.Session)
    response_one = Mock(spec=requests.Response)
    response_two = Mock(spec=requests.Response)
    response_one.json.return_value = {
        'data': [{'id': '1', 'attributes': {'name': 'Checking'}}],
        'links': {'next': 'https://firefly.example/api/v1/accounts?page=2'},
    }
    response_two.json.return_value = {
        'data': [{'id': '2', 'attributes': {'name': 'Savings'}}],
        'links': {'next': None},
    }
    response_one.raise_for_status.return_value = None
    response_two.raise_for_status.return_value = None
    session.get.side_effect = [response_one, response_two]

    accounts = fetch_asset_accounts(_settings(), session=session)

    assert [acct['id'] for acct in accounts] == ['1', '2']
    assert session.get.call_count == 2


def test_fetch_asset_accounts_errors_when_empty() -> None:
    session = Mock(spec=requests.Session)
    response = Mock(spec=requests.Response)
    response.json.return_value = {'data': [], 'links': {'next': None}}
    response.raise_for_status.return_value = None
    session.get.return_value = response

    with pytest.raises(ValueError, match='No asset accounts'):
        fetch_asset_accounts(_settings(), session=session)


def test_format_account_label_includes_masked_number() -> None:
    label = format_account_label({'id': '99', 'attributes': {'name': 'Checking', 'account_number': '123456789'}})
    assert 'Checking' in label
    assert '#*****6789' in label


def test_upload_transactions_posts_payload() -> None:
    session = Mock(spec=requests.Session)
    response = Mock(spec=requests.Response)
    response.raise_for_status.return_value = None
    response.text = '{"data":[]}'
    session.post.return_value = response
    payload = replace(_make_payload(), transactions=[])

    result = upload_transactions(_settings(), payload, session=session)

    assert result is response
    session.post.assert_called_once()
    call = session.post.call_args
    assert call.args[0].endswith('/transactions')
    assert call.kwargs['json'] == payload.to_dict()
    headers = call.kwargs['headers']
    assert headers['Authorization'].startswith('Bearer ')


def test_write_firefly_payloads(tmp_path: Path) -> None:
    split = _make_split()
    payloads = [replace(_make_payload(), transactions=[split])]
    output_path = tmp_path / 'payloads.json'
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        _ = (error, verbose_only)
        messages.append(message)

    write_firefly_payloads(payloads, output_path, emit=emit)

    assert json.loads(output_path.read_text(encoding='utf-8')) == [payloads[0].to_dict()]
    assert any('payloads.json' in msg for msg in messages)


def test_firefly_payload_serialization_handles_deposits() -> None:
    split = replace(
        _make_split(),
        type='deposit',
        date='2025-01-02',
        amount='25.00',
        description='Paycheck',
        external_id='xyz',
        notes='Paycheck',
        internal_reference='xyz',
        source_id=None,
        destination_id=7,
    )
    payload = replace(_make_payload(transactions=[split]), apply_rules=False, fire_webhooks=False)

    serialized = cast('dict[str, object]', payload.to_dict())
    transactions = cast('list[dict[str, object]]', serialized['transactions'])
    txn = transactions[0]
    assert txn['type'] == 'deposit'
    assert txn['destination_id'] == 7
    assert 'source_id' not in txn
    assert 'source_name' not in txn
    assert 'destination_name' not in txn


def test_upload_firefly_payloads_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload()
    called: list[dict[str, object]] = []

    def fake_upload_transactions(settings: FireflySettings, payload_arg: FireflyPayload) -> SimpleNamespace:
        _ = settings
        called.append(payload_arg.to_dict())
        return SimpleNamespace(status_code=200, text='{}', json=lambda: {'data': []})

    monkeypatch.setattr('firefly_preimporter.firefly_api.upload_transactions', fake_upload_transactions)
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        if not verbose_only:
            messages.append(f'{"ERROR" if error else "INFO"}: {message}')

    exit_code = upload_firefly_payloads([payload], _settings(), emit=emit)
    assert exit_code == 0
    assert called == [payload.to_dict()]
    assert any('Firefly upload 2025-01-01 "Coffee" - done' in msg for msg in messages)


def test_upload_firefly_payloads_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload()
    response = Response()
    response.status_code = 422
    response._content = b'{"message":"Invalid"}'
    http_error = HTTPError('422 Client Error')
    http_error.response = response  # type: ignore[assignment]

    def fake_upload_transactions(settings: FireflySettings, payload_arg: FireflyPayload) -> SimpleNamespace:
        _ = (settings, payload_arg)
        raise http_error

    monkeypatch.setattr('firefly_preimporter.firefly_api.upload_transactions', fake_upload_transactions)
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        if not verbose_only:
            messages.append(f'{"ERROR" if error else "INFO"}: {message}')

    exit_code = upload_firefly_payloads([payload], _settings(), emit=emit)
    assert exit_code == 1
    assert any('failed' in msg for msg in messages)
    assert any('Invalid' in msg for msg in messages)


def test_upload_firefly_payloads_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload()
    response = Response()
    response.status_code = 422
    response._content = (  # type: ignore[attr-defined]
        b'{"message":"Duplicate of transaction #5899.","errors":{"transactions.0.description":["Duplicate"]}}'
    )
    http_error = HTTPError('422 Client Error')
    http_error.response = response  # type: ignore[assignment]

    def fake_upload_transactions(settings: FireflySettings, payload_arg: FireflyPayload) -> SimpleNamespace:
        _ = (settings, payload_arg)
        raise http_error

    monkeypatch.setattr('firefly_preimporter.firefly_api.upload_transactions', fake_upload_transactions)
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        if not verbose_only:
            messages.append(f'{"ERROR" if error else "INFO"}: {message}')

    exit_code = upload_firefly_payloads([payload], _settings(), emit=emit)
    assert exit_code == 0
    assert any('duplicate' in msg.lower() for msg in messages)
    assert all('failed' not in msg.lower() for msg in messages)


def test_upload_firefly_payloads_applies_batch_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload()

    def fake_upload_transactions(settings: FireflySettings, payload_arg: FireflyPayload) -> SimpleNamespace:
        _ = (settings, payload_arg)
        return SimpleNamespace(
            status_code=200,
            text='{"data":[{"id":"123","attributes":{"transactions":[{"transaction_journal_id":"456","tags":["old"]}]}}]}',
            json=lambda: {
                'data': [
                    {
                        'id': '123',
                        'attributes': {'transactions': [{'transaction_journal_id': '456', 'tags': ['old']}]},
                    },
                ],
            },
        )

    monkeypatch.setattr('firefly_preimporter.firefly_api.upload_transactions', fake_upload_transactions)

    post_calls: list[tuple[str, dict[str, object]]] = []
    put_calls: list[tuple[str, dict[str, object]]] = []

    class DummyResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.text = '{}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {}

    def fake_post(url: str, **kwargs: object) -> DummyResponse:
        post_calls.append((url, kwargs))
        return DummyResponse()

    def fake_put(url: str, **kwargs: object) -> DummyResponse:
        put_calls.append((url, kwargs))
        return DummyResponse()

    monkeypatch.setattr('firefly_preimporter.firefly_api.requests.post', fake_post)
    monkeypatch.setattr('firefly_preimporter.firefly_api.requests.put', fake_put)

    exit_code = upload_firefly_payloads([payload], _settings(), emit=lambda *_a, **_k: None, batch_tag='ff tag')
    assert exit_code == 0
    assert post_calls, 'expected tag creation call'
    assert put_calls, 'expected tag application call'
    _, put_kwargs = put_calls[0]
    body = cast('dict[str, object]', put_kwargs['json'])
    transactions = cast('list[dict[str, object]]', body['transactions'])
    assert transactions[0]['tags'] == ['old', 'ff tag']


def test_extract_uploaded_groups_parses_transactions() -> None:
    payload = {
        'data': [
            {
                'id': '123',
                'attributes': {
                    'transactions': [
                        {'transaction_journal_id': '77', 'tags': ['foo']},
                        {'transaction_journal_id': '89', 'tags': []},
                    ],
                },
            },
        ],
    }
    resp = Response()
    resp.status_code = 200
    resp._content = json.dumps(payload).encode('utf-8')  # type: ignore[attr-defined]

    groups = firefly_api._extract_uploaded_groups(resp)

    assert groups == [UploadedGroup(group_id=123, journals={77: ['foo'], 89: []})]


def test_extract_uploaded_groups_ignores_bad_payload() -> None:
    class BadResponse(Response):
        def json(self) -> dict[str, object]:
            raise ValueError('boom')

    assert firefly_api._extract_uploaded_groups(BadResponse()) == []


def test_ensure_tag_exists_treats_422_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            error = HTTPError('422')
            error.response = SimpleNamespace(status_code=422)
            raise error

    monkeypatch.setattr(firefly_api.requests, 'post', lambda *_, **__: DummyResponse())

    firefly_api._ensure_tag_exists(_settings(), 'tag-ok')


def test_apply_batch_tag_calls_append(monkeypatch: pytest.MonkeyPatch) -> None:
    groups = [UploadedGroup(group_id=55, journals={101: ['existing']})]
    called: list[tuple[int, dict[int, list[str]], str]] = []

    def fake_append(
        settings: FireflySettings,
        group_id: int,
        journal_map: dict[int, list[str]],
        *,
        tag: str,
    ) -> SimpleNamespace:
        _ = settings
        called.append((group_id, journal_map, tag))
        return SimpleNamespace(text='{}')

    monkeypatch.setattr(firefly_api, '_ensure_tag_exists', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(firefly_api, '_append_tag_to_group', fake_append)

    firefly_api._apply_batch_tag(_settings(), tag='ff', groups=groups, emit=lambda *_a, **_k: None)

    assert called == [(55, {101: ['existing']}, 'ff')]


def test_mask_account_number_masks_all_but_last_four() -> None:
    assert firefly_api._mask_account_number('1234567890') == '******7890'


def test_mask_account_number_preserves_short_values() -> None:
    assert firefly_api._mask_account_number('123') == '123'


def test_format_firefly_status_truncates_description() -> None:
    payload = replace(
        _make_payload(),
        transactions=[
            replace(
                _make_split(),
                description='This is a very long description that should truncate',
            ),
        ],
    )
    label = firefly_api._format_firefly_status(payload)
    assert label.startswith('2025-01-01 "This is a very')
    assert label.endswith('…"')


def test_format_firefly_status_handles_missing_transactions() -> None:
    payload = replace(_make_payload(), transactions=[])
    label = firefly_api._format_firefly_status(payload)
    assert label == '? ""'


def test_merge_tags_removes_duplicates_and_blanks() -> None:
    merged = firefly_api._merge_tags(['alpha', '', 'bravo'], 'alpha')
    assert merged == ['alpha', 'bravo']


def test_emit_response_snippet_handles_long_and_empty() -> None:
    messages: list[tuple[str, bool, bool]] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        messages.append((message, error, verbose_only))

    long_text = 'x' * 600
    firefly_api._emit_response_snippet(emit, long_text)
    assert '…' in messages[0][0]

    firefly_api._emit_response_snippet(emit, '', error=True, verbose_only=True)
    assert '<empty response body>' in messages[1][0]
    assert messages[1][1] is True
    assert messages[1][2] is True


def test_verify_option_returns_cert_path(tmp_path: Path) -> None:
    cert_path = tmp_path / 'ca.pem'
    cert_path.write_text('cert', encoding='utf-8')
    settings = replace(_settings(), ca_cert_path=cert_path)

    result = firefly_api._verify_option(settings)

    assert result == str(cert_path)


def test_fetch_asset_accounts_handles_non_list_payload() -> None:
    session = Mock(spec=requests.Session)
    response_one = Mock(spec=requests.Response)
    response_two = Mock(spec=requests.Response)
    response_one.json.return_value = {
        'data': 'oops',
        'links': {'next': 'https://firefly.example/api/v1/accounts?page=2'},
    }
    response_two.json.return_value = {
        'data': [{'id': '2', 'attributes': {'name': 'Savings'}}],
        'links': [],
    }
    response_one.raise_for_status.return_value = None
    response_two.raise_for_status.return_value = None
    session.get.side_effect = [response_one, response_two]

    accounts = fetch_asset_accounts(_settings(), session=session)

    assert [acct['id'] for acct in accounts] == ['2']


def test_extract_uploaded_groups_handles_non_list_data() -> None:
    response = Response()
    response.status_code = 200
    response._content = b'{"data": {"id": "1"}}'  # type: ignore[attr-defined]

    assert firefly_api._extract_uploaded_groups(response) == []


def test_extract_uploaded_groups_handles_single_dict_payload() -> None:
    payload = {
        'data': {
            'id': '555',
            'attributes': {
                'transactions': [
                    {'transaction_journal_id': '919', 'tags': ['foo', 'bar']},
                ],
            },
        },
    }
    resp = Response()
    resp._content = json.dumps(payload).encode('utf-8')  # type: ignore[attr-defined]
    resp.status_code = 200

    groups = firefly_api._extract_uploaded_groups(resp)

    assert groups == [UploadedGroup(group_id=555, journals={919: ['foo', 'bar']})]


def test_apply_batch_tag_logs_and_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        _ = verbose_only
        prefix = 'ERROR:' if error else 'INFO:'
        messages.append(f'{prefix} {message}')

    response = SimpleNamespace(status_code=500, text='boom')
    http_error = HTTPError('500')
    http_error.response = response  # type: ignore[assignment]
    monkeypatch.setattr(firefly_api, '_ensure_tag_exists', lambda *_a, **_k: (_ for _ in ()).throw(http_error))

    with pytest.raises(HTTPError):
        firefly_api._apply_batch_tag(
            _settings(),
            tag='tag',
            groups=[UploadedGroup(group_id=1, journals={1: ['existing']})],
            emit=emit,
        )

    assert any('Error uploading payload' in msg for msg in messages)
    assert any('Firefly response body: boom' in msg for msg in messages)


def test_apply_batch_tag_logs_and_raises_on_other_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        _ = verbose_only
        if error:
            messages.append(message)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise ValueError('kapow')

    monkeypatch.setattr(firefly_api, '_ensure_tag_exists', explode)

    with pytest.raises(ValueError, match='kapow'):
        firefly_api._apply_batch_tag(
            _settings(),
            tag='tag',
            groups=[UploadedGroup(group_id=1, journals={})],
            emit=emit,
        )

    assert any('Error uploading payload' in msg for msg in messages)


def test_upload_firefly_payloads_handles_general_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload()

    def boom(settings: FireflySettings, payload_arg: FireflyPayload) -> None:
        _ = (settings, payload_arg)
        raise RuntimeError('boom')

    monkeypatch.setattr('firefly_preimporter.firefly_api.upload_transactions', boom)
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        _ = verbose_only
        if error:
            messages.append(message)

    exit_code = upload_firefly_payloads([payload], _settings(), emit=emit)

    assert exit_code == 1
    assert any('failed' in msg for msg in messages)


def test_upload_firefly_payloads_handles_batch_tag_request_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_payload()

    def fake_upload_transactions(settings: FireflySettings, payload_arg: FireflyPayload) -> SimpleNamespace:
        _ = (settings, payload_arg)
        return SimpleNamespace(
            status_code=200,
            text='{}',
            json=lambda: {
                'data': [
                    {
                        'id': '1',
                        'attributes': {'transactions': [{'transaction_journal_id': '10', 'tags': []}]},
                    }
                ],
            },
        )

    def raise_request_exception(*_args: object, **_kwargs: object) -> None:
        raise RequestException('tag failure')

    monkeypatch.setattr('firefly_preimporter.firefly_api.upload_transactions', fake_upload_transactions)
    monkeypatch.setattr('firefly_preimporter.firefly_api._apply_batch_tag', raise_request_exception)
    messages: list[str] = []

    def emit(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        _ = verbose_only
        if error:
            messages.append(message)

    exit_code = upload_firefly_payloads([payload], _settings(), emit=emit, batch_tag='taggy')

    assert exit_code == 1
    assert any('Error uploading payload' in msg for msg in messages)
