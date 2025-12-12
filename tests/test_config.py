import textwrap
from pathlib import Path

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


def test_load_settings_uses_default_json_when_missing(tmp_path: Path) -> None:
    config_file = tmp_path / 'config.toml'
    config_file.write_text('personal_access_token = "abc"\n', encoding='utf-8')
    settings = load_settings(config_file)
    assert settings.default_json_config['flow'] == 'file'
