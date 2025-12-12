from unittest.mock import Mock

import requests
from firefly_preimporter.config import FireflySettings
from firefly_preimporter.uploader import FidiUploader

SECRET_PLACEHOLDER = 'sec' + 'ret'
TOKEN_PLACEHOLDER = 'tok' + 'en'


def _settings() -> FireflySettings:
    return FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/firefly',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={},
    )


def test_uploader_dry_run() -> None:
    uploader = FidiUploader(_settings(), dry_run=True)
    response = uploader.upload('csv', {'flow': 'file'})
    assert isinstance(response, requests.Response)
    assert response.status_code == 200


def test_uploader_posts_payload() -> None:
    session = Mock(spec=requests.Session)
    response = Mock(spec=requests.Response)
    session.post.return_value = response
    response.raise_for_status.return_value = None

    uploader = FidiUploader(_settings(), session=session)
    result = uploader.upload('csv-data', {'flow': 'file'})

    session.post.assert_called_once()
    kwargs = session.post.call_args.kwargs
    assert kwargs['timeout'] == 10
    assert kwargs['data']['secret'] == SECRET_PLACEHOLDER
    assert kwargs['headers']['Authorization'] == f'Bearer {TOKEN_PLACEHOLDER}'
    assert kwargs['files']['importable'][0] == 'transactions.csv'
    assert result is response
