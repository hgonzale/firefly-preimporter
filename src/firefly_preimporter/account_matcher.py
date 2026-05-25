"""AI-assisted account matching for CSV upload suggestions."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import requests

if TYPE_CHECKING:
    from firefly_preimporter.config import AzureAiSettings
    from firefly_preimporter.models import Transaction

LOGGER = logging.getLogger(__name__)

_MAX_NEW_TRANSACTIONS = 10


@dataclass(frozen=True, slots=True)
class AccountSuggestion:
    """A ranked AI suggestion for which account a file belongs to."""

    account_id: str
    account_name: str
    confidence: str  # "high" | "medium" | "low"
    reasons: list[str]


def _build_prompt(
    filename: str,
    new_transactions: list[Transaction],
    accounts: list[dict[str, Any]],
    recent_txns_by_account: dict[str, list[tuple[str, str]]],
) -> str:
    lines: list[str] = [
        "You are matching a bank statement CSV file to one of the user's financial accounts.",
        '',
        f'FILE: {filename}',
        '',
        f'SAMPLE TRANSACTIONS FROM FILE (up to {_MAX_NEW_TRANSACTIONS}):',
    ]
    for txn in new_transactions[:_MAX_NEW_TRANSACTIONS]:
        lines.append(f'  {txn.date} | {txn.description} | {txn.amount}')
    lines.append('')

    lines.append('AVAILABLE ACCOUNTS:')
    for account in accounts:
        acct_id = str(account.get('id', ''))
        attributes = account.get('attributes', {})
        name = ''
        acct_number = ''
        if isinstance(attributes, Mapping):
            attrs = cast('Mapping[str, object]', attributes)
            name = str(attrs.get('name') or '').strip()
            acct_number = str(attrs.get('account_number') or '').strip()
        number_suffix = f' (account number ends in {acct_number[-4:]})' if len(acct_number) >= 4 else ''
        lines.append(f'ID {acct_id}: "{name}"{number_suffix}')
        history = recent_txns_by_account.get(acct_id, [])
        if history:
            lines.append(f'  Recent transactions ({len(history)}):')
            for desc, amount in history:
                lines.append(f'    {desc} | {amount}')
        else:
            lines.append('  Recent transactions: (none)')
        lines.append('')

    lines += [
        'Which account does this file belong to? Consider:',
        '1. Does the filename contain the account number suffix or the account name?',
        "2. Do the merchants/payees AND amounts in the file match the account's history?",
        '   (Recurring amounts like subscriptions are strong signals.)',
        '',
        'Respond with valid JSON only (no markdown). Return up to 3 ranked suggestions, most likely first:',
        '{"suggestions": [{"account_id": <integer>, "confidence": "high"|"medium"|"low"}, ...],'
        ' "reasons": ["<brief reason>", ...]}',
        'Include at most 3 reasons. Each reason must fit on one line. Omit filler; be direct.',
    ]
    return '\n'.join(lines)


def suggest_account(
    filename: str,
    new_transactions: list[Transaction],
    accounts: list[dict[str, Any]],
    recent_txns_by_account: dict[str, list[tuple[str, str]]],
    *,
    ai_config: AzureAiSettings,
) -> list[AccountSuggestion]:
    """Return ranked AI suggestions for which account ``filename`` belongs to.

    Returns an empty list if the model call fails or the response cannot be parsed.
    """
    if not accounts:
        return []

    prompt = _build_prompt(filename, new_transactions, accounts, recent_txns_by_account)
    url = ai_config.endpoint.rstrip('/') + '/chat/completions'
    try:
        response = requests.post(
            url,
            headers={'Authorization': f'Bearer {ai_config.api_key}'},
            json={'model': ai_config.model, 'messages': [{'role': 'user', 'content': prompt}]},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.debug('Azure AI account suggestion API error: %s', exc)
        return []

    content = (response.json().get('choices', [{}])[0].get('message', {}).get('content') or '').strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        LOGGER.debug('Azure AI response is not valid JSON: %.200s', content)
        return []

    raw_suggestions = parsed.get('suggestions', [])
    raw_reasons = parsed.get('reasons', [])
    reasons: list[str] = []
    if isinstance(raw_reasons, list):
        reasons = [str(r) for r in cast('list[object]', raw_reasons) if r]
    if not isinstance(raw_suggestions, list):
        LOGGER.debug('Azure AI "suggestions" field is not a list')
        return []

    account_names: dict[str, str] = {}
    for account in accounts:
        acct_id = str(account.get('id', ''))
        attributes = account.get('attributes', {})
        if isinstance(attributes, Mapping):
            attrs = cast('Mapping[str, object]', attributes)
            name = str(attrs.get('name') or '').strip()
            account_names[acct_id] = name or f'Account {acct_id}'

    valid_ids = {str(a.get('id', '')) for a in accounts}
    results: list[AccountSuggestion] = []
    for item in cast('list[object]', raw_suggestions):
        if not isinstance(item, Mapping):
            continue
        item_map = cast('Mapping[str, object]', item)
        account_id = str(item_map.get('account_id', ''))
        confidence = str(item_map.get('confidence', 'low'))
        if account_id not in valid_ids:
            LOGGER.debug('AI suggested unknown account_id %s — skipping', account_id)
            continue
        if confidence not in {'high', 'medium', 'low'}:
            confidence = 'low'
        results.append(
            AccountSuggestion(
                account_id=account_id,
                account_name=account_names.get(account_id, f'Account {account_id}'),
                confidence=confidence,
                reasons=reasons,
            )
        )

    return results[:3]
