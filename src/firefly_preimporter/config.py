"""Configuration utilities and dataclasses for Firefly Preimporter."""

from __future__ import annotations

import logging
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH: Path = Path.home() / '.local/etc/firefly_import.toml'
"""Default location for the user provided TOML configuration file."""


@dataclass(frozen=True, slots=True)
class AzureAiSettings:
    """Optional settings for AI-assisted account matching via Azure AI Foundry."""

    endpoint: str
    api_key: str
    model: str
    history_days: int
    max_history_per_account: int


@dataclass(frozen=True, slots=True)
class CommonSettings:
    """Shared settings used across all upload paths."""

    personal_access_token: str
    request_timeout: int
    ca_cert_path: Path | None = None
    default_upload: str | None = None
    azure_ai: AzureAiSettings | None = None


@dataclass(frozen=True, slots=True)
class FidiSettings:
    """Settings for the FiDI upload path."""

    import_secret: str
    autoupload_url: str
    json_config: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FireflyApiSettings:
    """Settings for the Firefly III API upload path."""

    api_base: str
    allow_duplicates: bool = False


@dataclass(frozen=True, slots=True)
class FireflyPreimporterSettings:
    """Structured settings for Firefly Preimporter."""

    common: CommonSettings
    fidi: FidiSettings | None = None
    firefly_api: FireflyApiSettings | None = None


def _prepare_settings(raw: Mapping[str, Any]) -> FireflyPreimporterSettings:
    """Convert a raw dictionary into ``FireflyPreimporterSettings`` with proper types."""

    raw_common = raw.get('common', {})

    ca_path = raw_common.get('ca_cert_path')
    resolved_ca = Path(ca_path).expanduser() if isinstance(ca_path, str) and ca_path else None

    upload_choice = str(raw_common.get('default_upload', '') or '').strip().lower()
    if upload_choice not in {'fidi', 'firefly'}:
        upload_choice = ''

    raw_azure = raw_common.get('azure_ai') or {}
    azure_ai: AzureAiSettings | None = None
    if isinstance(raw_azure, Mapping) and raw_azure.get('endpoint') and raw_azure.get('api_key'):
        azure_ai = AzureAiSettings(
            endpoint=str(raw_azure['endpoint']),
            api_key=str(raw_azure['api_key']),
            model=str(raw_azure.get('model', 'gpt-4o-mini')),
            history_days=int(raw_azure.get('history_days', 60)),
            max_history_per_account=int(raw_azure.get('max_history_per_account', 100)),
        )

    common = CommonSettings(
        personal_access_token=str(raw_common['personal_access_token']),
        request_timeout=int(raw_common['request_timeout']),
        ca_cert_path=resolved_ca,
        default_upload=upload_choice or None,
        azure_ai=azure_ai,
    )

    fidi: FidiSettings | None = None
    if 'fidi' in raw:
        raw_fidi = raw['fidi']
        fidi = FidiSettings(
            import_secret=str(raw_fidi['import_secret']),
            autoupload_url=str(raw_fidi['autoupload_url']),
            json_config=dict(raw_fidi.get('json_config', {})),
        )

    firefly_api: FireflyApiSettings | None = None
    if 'firefly_api' in raw:
        raw_fa = raw['firefly_api']
        firefly_api = FireflyApiSettings(
            api_base=str(raw_fa['api_base']),
            allow_duplicates=bool(raw_fa.get('allow_duplicates', False)),
        )

    return FireflyPreimporterSettings(
        common=common,
        fidi=fidi,
        firefly_api=firefly_api,
    )


def load_settings(path: Path | None = None) -> FireflyPreimporterSettings:
    """Load ``FireflyPreimporterSettings`` from the provided TOML file path."""

    config_path = (path or DEFAULT_CONFIG_PATH).expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f'Configuration file not found: {config_path}')

    # Check file permissions (Unix-like systems only)
    try:
        file_stat = config_path.stat()
        if file_stat.st_mode & stat.S_IROTH:
            LOGGER.warning(
                'Config file %s is world-readable and may contain sensitive tokens. '
                'Consider restricting permissions with: chmod 600 %s',
                config_path,
                config_path,
            )
        if file_stat.st_mode & stat.S_IRGRP:
            LOGGER.warning(
                'Config file %s is group-readable and may contain sensitive tokens. '
                'Consider restricting permissions with: chmod 600 %s',
                config_path,
                config_path,
            )
    except (OSError, AttributeError):
        # OSError: stat failed, AttributeError: Windows doesn't have st_mode
        pass

    with config_path.open('rb') as handle:
        raw = tomllib.load(handle)

    if 'firefly-api' in raw:
        raw['firefly_api'] = raw.pop('firefly-api')
    common = raw.get('common', {})
    if 'azure-ai' in common:
        common['azure_ai'] = common.pop('azure-ai')
    if 'fidi' in raw and 'json-config' in raw['fidi']:
        raw['fidi']['json_config'] = raw['fidi'].pop('json-config')

    return _prepare_settings(raw)
