import stat
import sys
import textwrap
from pathlib import Path

import pytest

from firefly_preimporter.config import AzureAiSettings, FireflyPreimporterSettings, load_settings

TOKEN_PLACEHOLDER = 'token-' + 'placeholder'
IMPORT_PLACEHOLDER = 'import-' + 'placeholder'

_MINIMAL_TOML = textwrap.dedent(
    f"""
    [common]
    personal_access_token = "{TOKEN_PLACEHOLDER}"
    request_timeout = 30
    """
)


def test_load_settings_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / 'missing.toml'
    with pytest.raises(FileNotFoundError):
        load_settings(missing)


def test_load_settings_new_structure(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text(
        textwrap.dedent(
            f"""
            [common]
            personal_access_token = "{TOKEN_PLACEHOLDER}"
            request_timeout = 45
            default_upload = "firefly"

            [fidi]
            import_secret = "{IMPORT_PLACEHOLDER}"
            autoupload_url = "https://fidi.example.com/autoupload"

            [fidi.json-config]
            flow = "json"
            headers = false
            date = "Y-m-d"
            delimiter = "comma"
            rules = true
            skip_form = true
            add_import_tag = true
            duplicate_detection_method = "cell"
            unique_column_type = "external-id"
            unique_column_index = 0

            [firefly-api]
            api_base = "https://firefly.example.com/api/v1"
            allow_duplicates = false
            """
        ),
        encoding='utf-8',
    )

    settings = load_settings(config_file)
    assert isinstance(settings, FireflyPreimporterSettings)
    assert settings.common.personal_access_token == TOKEN_PLACEHOLDER
    assert settings.common.request_timeout == 45
    assert settings.common.default_upload == 'firefly'
    assert settings.fidi is not None
    assert settings.fidi.import_secret == IMPORT_PLACEHOLDER
    assert settings.fidi.autoupload_url == 'https://fidi.example.com/autoupload'
    assert settings.fidi.json_config['flow'] == 'json'
    assert settings.fidi.json_config['headers'] is False
    assert settings.firefly_api is not None
    assert settings.firefly_api.api_base == 'https://firefly.example.com/api/v1'
    assert settings.firefly_api.allow_duplicates is False


def test_load_settings_optional_sections_absent(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text(_MINIMAL_TOML, encoding='utf-8')
    settings = load_settings(config_file)
    assert settings.fidi is None
    assert settings.firefly_api is None
    assert settings.common.default_upload is None


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix file permissions not available on Windows')
def test_load_settings_warns_on_world_readable_config(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test that a warning is logged when config file is world-readable."""
    config_file = tmp_path / 'config.toml'
    config_file.write_text(_MINIMAL_TOML, encoding='utf-8')

    # Make file world-readable (chmod 644)
    config_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

    with caplog.at_level('WARNING'):
        load_settings(config_file)

    assert 'world-readable' in caplog.text
    assert 'chmod 600' in caplog.text


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix file permissions not available on Windows')
def test_load_settings_warns_on_group_readable_config(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test that a warning is logged when config file is group-readable."""
    config_file = tmp_path / 'config.toml'
    config_file.write_text(_MINIMAL_TOML, encoding='utf-8')

    # Make file group-readable (chmod 640)
    config_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)

    with caplog.at_level('WARNING'):
        load_settings(config_file)

    assert 'group-readable' in caplog.text
    assert 'chmod 600' in caplog.text


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix file permissions not available on Windows')
def test_load_settings_no_warning_on_secure_permissions(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test that no warning is logged when config file has secure permissions (chmod 600)."""
    config_file = tmp_path / 'config.toml'
    config_file.write_text(_MINIMAL_TOML, encoding='utf-8')

    # Make file owner-only readable (chmod 600)
    config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    with caplog.at_level('WARNING'):
        load_settings(config_file)

    assert 'readable' not in caplog.text


def test_load_settings_azure_ai_absent_is_none(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text(_MINIMAL_TOML, encoding='utf-8')
    settings = load_settings(config_file)
    assert settings.common.azure_ai is None


def test_load_settings_azure_ai_configured(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text(
        textwrap.dedent(
            f"""
            [common]
            personal_access_token = "{TOKEN_PLACEHOLDER}"
            request_timeout = 30

            [common.azure-ai]
            endpoint = "https://my-hub.openai.azure.com/"
            api_key = "secret-key"
            model = "gpt-4o"
            history_days = 90
            max_history_per_account = 50
            """
        ),
        encoding='utf-8',
    )
    settings = load_settings(config_file)
    assert isinstance(settings.common.azure_ai, AzureAiSettings)
    assert settings.common.azure_ai.endpoint == 'https://my-hub.openai.azure.com/'
    assert settings.common.azure_ai.model == 'gpt-4o'
    assert settings.common.azure_ai.history_days == 90
    assert settings.common.azure_ai.max_history_per_account == 50


def test_load_settings_azure_ai_defaults(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text(
        textwrap.dedent(
            f"""
            [common]
            personal_access_token = "{TOKEN_PLACEHOLDER}"
            request_timeout = 30

            [common.azure-ai]
            endpoint = "https://my-hub.openai.azure.com/"
            api_key = "secret-key"
            """
        ),
        encoding='utf-8',
    )
    settings = load_settings(config_file)
    assert settings.common.azure_ai is not None
    assert settings.common.azure_ai.model == 'gpt-4o-mini'
    assert settings.common.azure_ai.history_days == 60
    assert settings.common.azure_ai.max_history_per_account == 100


def test_load_settings_azure_ai_missing_key_is_none(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text(
        textwrap.dedent(
            f"""
            [common]
            personal_access_token = "{TOKEN_PLACEHOLDER}"
            request_timeout = 30

            [common.azure-ai]
            endpoint = "https://my-hub.openai.azure.com/"
            """
        ),
        encoding='utf-8',
    )
    settings = load_settings(config_file)
    assert settings.common.azure_ai is None


def test_load_settings_missing_required_field_raises(tmp_path: Path) -> None:
    """Missing personal_access_token in [common] raises KeyError."""
    config_file = tmp_path / 'config.toml'
    config_file.write_text(
        textwrap.dedent(
            """
            [common]
            request_timeout = 30
            """
        ),
        encoding='utf-8',
    )
    with pytest.raises(KeyError):
        load_settings(config_file)
