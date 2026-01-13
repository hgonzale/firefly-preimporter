import stat
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from firefly_preimporter.config import FireflySettings, load_settings

TOKEN_PLACEHOLDER = 'token-' + 'placeholder'
IMPORT_PLACEHOLDER = 'import-' + 'placeholder'


def test_load_settings_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / 'missing.toml'
    with pytest.raises(FileNotFoundError):
        load_settings(missing)


def test_load_settings_merges_overrides(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text(
        textwrap.dedent(
            f"""
            personal_access_token = "{TOKEN_PLACEHOLDER}"
            fidi_import_secret = "{IMPORT_PLACEHOLDER}"
            request_timeout = 45
            firefly_error_on_duplicate = false
            default_upload = "firefly"

            [default_json_config]
            flow = "json"
            headers = false

            [known_roles]
            memo = "description"
            """
        ),
        encoding='utf-8',
    )

    settings = load_settings(config_file)
    assert isinstance(settings, FireflySettings)
    assert settings.personal_access_token == TOKEN_PLACEHOLDER
    assert settings.fidi_import_secret == IMPORT_PLACEHOLDER
    assert settings.request_timeout == 45
    assert settings.default_json_config['flow'] == 'json'
    # default_json_config should retain unspecified defaults
    assert settings.default_json_config['duplicate_detection_method'] == 'cell'
    assert settings.default_json_config['ignore_duplicate_lines'] is True
    assert settings.default_json_config['ignore_duplicate_transactions'] is True
    assert settings.default_json_config['conversion'] is False
    assert settings.known_roles['memo'] == 'description'
    assert settings.firefly_error_on_duplicate is False
    assert settings.default_upload == 'firefly'


def test_load_settings_uses_default_json_when_missing(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text('personal_access_token = "abc"\n', encoding='utf-8')
    settings = load_settings(config_file)
    assert settings.default_json_config['flow'] == 'file'
    assert settings.firefly_error_on_duplicate is True
    assert settings.default_upload is None


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix file permissions not available on Windows')
def test_load_settings_warns_on_world_readable_config(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test that a warning is logged when config file is world-readable."""
    config_file = tmp_path / 'config.toml'
    config_file.write_text('personal_access_token = "abc"\n', encoding='utf-8')

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
    config_file.write_text('personal_access_token = "abc"\n', encoding='utf-8')

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
    config_file.write_text('personal_access_token = "abc"\n', encoding='utf-8')

    # Make file owner-only readable (chmod 600)
    config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    with caplog.at_level('WARNING'):
        load_settings(config_file)

    assert 'readable' not in caplog.text
