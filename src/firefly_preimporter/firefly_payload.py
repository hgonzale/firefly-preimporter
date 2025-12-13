"""Helpers to build Firefly III transaction payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from firefly_preimporter.models import ProcessingResult, Transaction


def _positive_amount(amount: str) -> tuple[str, str] | None:
    """Return (type, amount) tuple based on the sign of ``amount``."""

    try:
        value = Decimal(amount)
    except InvalidOperation:
        return None
    if value == 0:
        return None
    transaction_type = 'withdrawal' if value.is_signed() else 'deposit'
    return transaction_type, format(abs(value), 'f')


def _sanitize_description(description: str) -> str:
    text = description.strip() or 'Imported transaction'
    return text[:255]


@dataclass(slots=True)
class FireflyPayloadBuilder:
    """Aggregate transactions into a Firefly API payload."""

    tag: str
    error_on_duplicate: bool = True
    apply_rules: bool = True
    fire_webhooks: bool = True
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def add_result(self, result: ProcessingResult, *, account_id: str, currency_code: str) -> None:
        """Convert ``result`` transactions into Firefly entries."""

        for txn in result.transactions:
            entry = self._convert_transaction(txn, account_id=account_id, currency_code=currency_code)
            if entry:
                self.transactions.append(entry)

    def _convert_transaction(
        self,
        txn: Transaction,
        *,
        account_id: str,
        currency_code: str,
    ) -> dict[str, Any] | None:
        outcome = _positive_amount(txn.amount)
        if outcome is None:
            return None
        transaction_type, amount = outcome
        description = _sanitize_description(txn.description)
        entry: dict[str, Any] = {
            'type': transaction_type,
            'date': txn.date,
            'amount': amount,
            'currency_code': currency_code,
            'description': txn.description,
            'external_id': txn.transaction_id,
            'notes': txn.description,
            'tags': [self.tag],
            'error_if_duplicate_hash': self.error_on_duplicate,
            'internal_reference': txn.transaction_id,
        }
        if transaction_type == 'withdrawal':
            entry['source_id'] = int(account_id)
            entry['destination_name'] = description
        else:
            entry['destination_id'] = int(account_id)
            entry['source_name'] = description
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {
            'group_title': self.tag,
            'error_if_duplicate_hash': self.error_on_duplicate,
            'apply_rules': self.apply_rules,
            'fire_webhooks': self.fire_webhooks,
            'transactions': self.transactions,
        }
