"""Integration test: AI account matcher against the real Azure AI endpoint."""
from __future__ import annotations

import pytest

from firefly_preimporter.account_matcher import suggest_account


def test_ai_suggestion_returns_results(settings):
    """suggest_account makes a real API call and returns at least one suggestion."""
    if settings.common.azure_ai is None:
        pytest.skip('No [common.azure-ai] config — skipping AI integration test')

    accounts = [
        {'id': '1', 'attributes': {'name': 'Checking', 'account_number': '0001'}},
        {'id': '2', 'attributes': {'name': 'Savings', 'account_number': '0002'}},
    ]

    suggestions = suggest_account(
        filename='checking_statement_0001.csv',
        new_transactions=[],
        accounts=accounts,
        recent_txns_by_account={'1': [], '2': []},
        ai_config=settings.common.azure_ai,
    )

    assert len(suggestions) >= 1, 'Expected at least one suggestion from the AI'
    assert suggestions[0].account_id in {'1', '2'}
    assert suggestions[0].confidence in {'high', 'medium', 'low'}
    assert suggestions[0].reasoning
