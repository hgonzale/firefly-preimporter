"""Integration test: Firefly III API connectivity against the real instance."""
from __future__ import annotations

import pytest

from firefly_preimporter.firefly_api import fetch_asset_accounts


def test_fetch_asset_accounts_returns_results(settings):
    """fetch_asset_accounts makes a real API call and returns at least one account."""
    if settings.firefly_api is None:
        pytest.skip('No [firefly-api] config — skipping Firefly API integration test')

    accounts = fetch_asset_accounts(settings)

    assert len(accounts) >= 1, 'Expected at least one asset account from Firefly'
    first = accounts[0]
    assert 'id' in first
    assert 'attributes' in first
