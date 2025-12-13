from unittest.mock import Mock

import pytest

import requests
from firefly_preimporter.config import FireflySettings
from firefly_preimporter.firefly_api import fetch_asset_accounts, format_account_label, upload_transactions


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


def test_format_account_label_includes_number() -> None:
    label = format_account_label({'id': '99', 'attributes': {'name': 'Checking', 'account_number': '1234'}})
    assert 'Checking' in label
    assert '#1234' in label


def test_upload_transactions_posts_payload() -> None:
    session = Mock(spec=requests.Session)
    response = Mock(spec=requests.Response)
    response.raise_for_status.return_value = None
    response.text = '{"data":[]}'
    session.post.return_value = response
    payload = {'transactions': []}

    result = upload_transactions(_settings(), payload, session=session)

    assert result is response
    session.post.assert_called_once()
    call = session.post.call_args
    assert call.args[0].endswith('/transactions')
    assert call.kwargs['json'] == payload
    headers = call.kwargs['headers']
    assert headers['Authorization'].startswith('Bearer ')
