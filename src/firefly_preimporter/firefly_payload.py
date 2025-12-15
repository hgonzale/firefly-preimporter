"""Helpers to build Firefly III transaction payloads."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from firefly_preimporter.models import (
    FireflyPayload,
    FireflyTransactionSplit,
    ProcessingResult,
    Transaction,
)


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


class FireflyPayloadBuilder:
    """Aggregate normalized transactions into Firefly API payloads."""

    def __init__(
        self,
        tag: str,
        *,
        error_on_duplicate: bool = True,
        apply_rules: bool = True,
        fire_webhooks: bool = True,
    ) -> None:
        self.tag = tag
        self.error_on_duplicate = error_on_duplicate
        self.apply_rules = apply_rules
        self.fire_webhooks = fire_webhooks
        self.payloads: list[FireflyPayload] = []

    def add_result(self, result: ProcessingResult, *, account_id: str, currency_code: str) -> None:
        """Convert ``result`` transactions into Firefly payloads."""

        for txn in result.transactions:
            payload = self._convert_transaction(txn, account_id=account_id, currency_code=currency_code)
            if payload:
                self.payloads.append(payload)

    def _convert_transaction(
        self,
        txn: Transaction,
        *,
        account_id: str,
        currency_code: str,
    ) -> FireflyPayload | None:
        outcome = _positive_amount(txn.amount)
        if outcome is None:
            return None
        transaction_type, amount = outcome
        description = _sanitize_description(txn.description)
        split = FireflyTransactionSplit(
            type=transaction_type,
            date=txn.date,
            amount=amount,
            currency_code=currency_code,
            description=description,
            external_id=txn.transaction_id,
            notes=txn.description,
            error_if_duplicate_hash=self.error_on_duplicate,
            internal_reference=txn.transaction_id,
            tags=[],
        )
        account_identifier = int(account_id)
        if transaction_type == 'withdrawal':
            split.source_id = account_identifier
            split.destination_name = '(no name)'
        else:
            split.destination_id = account_identifier
            split.source_name = '(no name)'
        return FireflyPayload(
            error_if_duplicate_hash=self.error_on_duplicate,
            apply_rules=self.apply_rules,
            fire_webhooks=self.fire_webhooks,
            transactions=[split],
        )

    def has_payloads(self) -> bool:
        return bool(self.payloads)

    def to_payloads(self) -> list[FireflyPayload]:
        return list(self.payloads)
