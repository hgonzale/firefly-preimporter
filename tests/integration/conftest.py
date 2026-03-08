"""Shared fixtures for integration tests.

Integration tests require a real config file at the default location
(~/.local/etc/firefly_import.toml). They are skipped automatically if the
file is absent, so they never run in CI.
"""
from __future__ import annotations

import pytest

from firefly_preimporter.config import DEFAULT_CONFIG_PATH, load_settings


@pytest.fixture(scope='session')
def settings():
    if not DEFAULT_CONFIG_PATH.expanduser().is_file():
        pytest.skip(f'No config file at {DEFAULT_CONFIG_PATH} — skipping integration tests')
    return load_settings()
