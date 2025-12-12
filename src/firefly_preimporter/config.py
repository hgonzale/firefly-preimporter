"""Configuration utilities and dataclasses for Firefly Preimporter."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH: Path = Path.home() / '.local/etc/firefly_import.toml'
"""Default location for the user provided TOML configuration file."""

DEFAULT_JSON_CONFIG: dict[str, Any] = {
    'date': 'Y-m-d',
    'delimiter': 'comma',
    'headers': True,
    'rules': True,
    'skip_form': True,
    'add_import_tag': True,
    'duplicate_detection_method': 'cell',
    'ignore_duplicate_lines': True,
    'ignore_duplicate_transactions': True,
    'unique_column_type': 'external-id',
    'unique_column_index': 0,
    'default_account': 0,
    'flow': 'file',
    'conversion': False,
    'mapping': [],
    'version': 3,
}
"""Baseline FiDI JSON configuration that can be overridden via TOML."""

BASE_SETTINGS: dict[str, Any] = {
    'fidi_import_secret': '',
    'personal_access_token': '',
    'fidi_autoupload_url': 'https://example.com/fidi/autoupload',
    'firefly_api_base': 'https://example.com/firefly/api/v1',
    'ca_cert_path': None,
    'request_timeout': 30,
    'unique_column_role': 'internal_reference',
    'date_column_role': 'date_transaction',
    'known_roles': {
        'dtposted': 'date_transaction',
        'trnamt': 'amount',
        'name': 'description',
        'fitid': 'internal_reference',
        'acctid': 'account-number',
    },
    'default_json_config': DEFAULT_JSON_CONFIG,
}
"""Default settings merged with any local overrides."""


@dataclass(frozen=True, slots=True)
class FireflySettings:
    """Structured settings required to interact with Firefly III and FiDI."""

    fidi_import_secret: str
    personal_access_token: str
    fidi_autoupload_url: str
    firefly_api_base: str
    ca_cert_path: Path | None
    request_timeout: int
    unique_column_role: str
    date_column_role: str
    known_roles: Mapping[str, str]
    default_json_config: Mapping[str, Any]


def _merge_dict(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, returning a new dictionary."""

    merged: dict[str, Any] = dict(base)
    for key, value in overrides.items():
        if key in merged and isinstance(merged[key], Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _prepare_settings(raw: Mapping[str, Any]) -> FireflySettings:
    """Convert a raw dictionary into ``FireflySettings`` with proper types."""

    ca_path = raw.get('ca_cert_path')
    resolved_ca = Path(ca_path).expanduser() if isinstance(ca_path, str) and ca_path else None
    json_cfg = dict(raw.get('default_json_config', {}))
    known_roles = dict(raw.get('known_roles', {}))
    return FireflySettings(
        fidi_import_secret=str(raw.get('fidi_import_secret', '')),
        personal_access_token=str(raw.get('personal_access_token', '')),
        fidi_autoupload_url=str(raw.get('fidi_autoupload_url', '')),
        firefly_api_base=str(raw.get('firefly_api_base', '')),
        ca_cert_path=resolved_ca,
        request_timeout=int(raw.get('request_timeout', 30)),
        unique_column_role=str(raw.get('unique_column_role', 'internal_reference')),
        date_column_role=str(raw.get('date_column_role', 'date_transaction')),
        known_roles=known_roles,
        default_json_config=json_cfg,
    )


def load_settings(path: Path | None = None) -> FireflySettings:
    """Load ``FireflySettings`` from the provided TOML file path."""

    config_path = (path or DEFAULT_CONFIG_PATH).expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f'Configuration file not found: {config_path}')

    with config_path.open('rb') as handle:
        overrides = tomllib.load(handle)

    merged = _merge_dict(BASE_SETTINGS, overrides)
    if 'default_json_config' not in overrides:
        merged['default_json_config'] = dict(DEFAULT_JSON_CONFIG)
    return _prepare_settings(merged)
