from unittest.mock import Mock

import requests
from firefly_preimporter.config import CommonSettings, FidiSettings, FireflyApiSettings, FireflyPreimporterSettings
from firefly_preimporter.uploader import FidiUploader

SECRET_PLACEHOLDER = 'sec' + 'ret'
TOKEN_PLACEHOLDER = 'tok' + 'en'


def _settings() -> FireflyPreimporterSettings:
    return FireflyPreimporterSettings(
        common=CommonSettings(
            personal_access_token=TOKEN_PLACEHOLDER,
            request_timeout=10,
        ),
        fidi=FidiSettings(
            import_secret=SECRET_PLACEHOLDER,
            autoupload_url='https://example/fidi',
            json_config={},
        ),
        firefly_api=FireflyApiSettings(
            api_base='https://example/firefly',
        ),
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
