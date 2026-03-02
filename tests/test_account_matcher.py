"""Tests for account_matcher module."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from openai import OpenAIError

from firefly_preimporter.account_matcher import _build_prompt, suggest_account
from firefly_preimporter.config import AzureAiSettings
from firefly_preimporter.models import Transaction


def _ai_config() -> AzureAiSettings:
    return AzureAiSettings(
        endpoint='https://example.openai.azure.com/',
        api_key='test-key',
        model='gpt-4o-mini',
        history_days=60,
        max_history_per_account=100,
    )


def _accounts() -> list[dict[str, Any]]:
    return [
        {'id': '3', 'attributes': {'name': 'Chase Freedom', 'account_number': '123454521'}},
        {'id': '7', 'attributes': {'name': 'Home Depot Card', 'account_number': '88238823'}},
    ]


def _txns() -> list[Transaction]:
    return [
        Transaction(transaction_id='a', date='2025-01-03', description='WHOLE FOODS', amount='-87.42'),
        Transaction(transaction_id='b', date='2025-01-07', description='NETFLIX', amount='-15.99'),
    ]


def _recent() -> dict[str, list[tuple[str, str]]]:
    return {
        '3': [('WHOLE FOODS', '-87.42'), ('AMAZON', '-34.99'), ('NETFLIX', '-15.99')],
        '7': [('HOME DEPOT', '-142.50'), ("LOWE'S", '-89.00')],
    }


def _mock_client(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    mock = MagicMock()
    mock.return_value.chat.completions.create.return_value = completion
    return mock


# --- _build_prompt ---


def test_build_prompt_contains_filename() -> None:
    prompt = _build_prompt('statement_4521.csv', _txns(), _accounts(), _recent())
    assert 'statement_4521.csv' in prompt


def test_build_prompt_contains_transaction_descriptions() -> None:
    prompt = _build_prompt('file.csv', _txns(), _accounts(), _recent())
    assert 'WHOLE FOODS' in prompt
    assert 'NETFLIX' in prompt


def test_build_prompt_contains_account_names() -> None:
    prompt = _build_prompt('file.csv', _txns(), _accounts(), _recent())
    assert 'Chase Freedom' in prompt
    assert 'Home Depot Card' in prompt


def test_build_prompt_contains_account_number_suffix() -> None:
    prompt = _build_prompt('file.csv', _txns(), _accounts(), _recent())
    assert '4521' in prompt
    assert '8823' in prompt


def test_build_prompt_contains_recent_transactions() -> None:
    prompt = _build_prompt('file.csv', _txns(), _accounts(), _recent())
    assert 'AMAZON' in prompt
    assert 'HOME DEPOT' in prompt


def test_build_prompt_caps_new_transactions_at_ten() -> None:
    many_txns = [
        Transaction(transaction_id=str(i), date='2025-01-01', description=f'TXN-{i}', amount='-1.00') for i in range(20)
    ]
    prompt = _build_prompt('file.csv', many_txns, _accounts(), _recent())
    # Only first 10 should appear
    assert 'TXN-9' in prompt
    assert 'TXN-10' not in prompt


def test_build_prompt_handles_account_without_number() -> None:
    accounts = [{'id': '1', 'attributes': {'name': 'No Number Account', 'account_number': ''}}]
    prompt = _build_prompt('file.csv', [], accounts, {})
    assert 'No Number Account' in prompt
    assert 'ends in' not in prompt


def test_build_prompt_handles_no_recent_transactions() -> None:
    prompt = _build_prompt('file.csv', _txns(), _accounts(), {})
    assert '(none)' in prompt


# --- suggest_account ---


def test_suggest_account_returns_empty_when_no_accounts() -> None:
    result = suggest_account('file.csv', _txns(), [], {}, ai_config=_ai_config())
    assert result == []


def test_suggest_account_happy_path_single() -> None:
    response = json.dumps({
        'suggestions': [{'account_id': 3, 'confidence': 'high'}],
        'reasoning': 'Filename contains 4521 and transaction history matches.',
    })
    with patch('firefly_preimporter.account_matcher.OpenAI', _mock_client(response)):
        result = suggest_account('statement_4521.csv', _txns(), _accounts(), _recent(), ai_config=_ai_config())

    assert len(result) == 1
    assert result[0].account_id == '3'
    assert result[0].account_name == 'Chase Freedom'
    assert result[0].confidence == 'high'
    assert '4521' in result[0].reasoning


def test_suggest_account_returns_up_to_three() -> None:
    accounts = [{'id': str(i), 'attributes': {'name': f'Account {i}', 'account_number': ''}} for i in range(5)]
    response = json.dumps({
        'suggestions': [
            {'account_id': 0, 'confidence': 'high'},
            {'account_id': 1, 'confidence': 'medium'},
            {'account_id': 2, 'confidence': 'low'},
            {'account_id': 3, 'confidence': 'low'},
        ],
        'reasoning': 'Multiple candidates.',
    })
    with patch('firefly_preimporter.account_matcher.OpenAI', _mock_client(response)):
        result = suggest_account('file.csv', [], accounts, {}, ai_config=_ai_config())

    assert len(result) == 3


def test_suggest_account_filters_unknown_account_ids() -> None:
    response = json.dumps({
        'suggestions': [{'account_id': 999, 'confidence': 'high'}],
        'reasoning': 'Unknown.',
    })
    with patch('firefly_preimporter.account_matcher.OpenAI', _mock_client(response)):
        result = suggest_account('file.csv', _txns(), _accounts(), _recent(), ai_config=_ai_config())

    assert result == []


def test_suggest_account_normalises_invalid_confidence() -> None:
    response = json.dumps({
        'suggestions': [{'account_id': 3, 'confidence': 'very-sure'}],
        'reasoning': 'Sure.',
    })
    with patch('firefly_preimporter.account_matcher.OpenAI', _mock_client(response)):
        result = suggest_account('file.csv', _txns(), _accounts(), _recent(), ai_config=_ai_config())

    assert len(result) == 1
    assert result[0].confidence == 'low'


def test_suggest_account_returns_empty_on_invalid_json() -> None:
    with patch('firefly_preimporter.account_matcher.OpenAI', _mock_client('not json at all')):
        result = suggest_account('file.csv', _txns(), _accounts(), _recent(), ai_config=_ai_config())

    assert result == []


def test_suggest_account_returns_empty_on_api_error() -> None:
    mock = MagicMock()
    mock.return_value.chat.completions.create.side_effect = OpenAIError()
    with patch('firefly_preimporter.account_matcher.OpenAI', mock):
        result = suggest_account('file.csv', _txns(), _accounts(), _recent(), ai_config=_ai_config())

    assert result == []


def test_suggest_account_returns_empty_when_suggestions_not_list() -> None:
    response = json.dumps({'suggestions': 'not-a-list', 'reasoning': 'Oops.'})
    with patch('firefly_preimporter.account_matcher.OpenAI', _mock_client(response)):
        result = suggest_account('file.csv', _txns(), _accounts(), _recent(), ai_config=_ai_config())

    assert result == []
