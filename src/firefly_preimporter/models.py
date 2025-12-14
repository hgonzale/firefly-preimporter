"""Shared data models used across Firefly Preimporter modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type-checking imports only
    from pathlib import Path


class SourceFormat(str, Enum):
    """Supported input formats detected by the pipeline."""

    CSV = 'csv'
    OFX = 'ofx'
    UNKNOWN = 'unknown'


@dataclass(slots=True)
class Transaction:
    """Normalized transaction record ready for FiDI consumption."""

    transaction_id: str
    date: str
    description: str
    amount: str


@dataclass(slots=True)
class ProcessingJob:
    """Description of the work needed to convert an input file."""

    source_path: Path
    source_format: SourceFormat


@dataclass(slots=True)
class ProcessingResult:
    """Outcome of processing an input file."""

    job: ProcessingJob
    transactions: list[Transaction] = field(default_factory=list)
    account_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def has_transactions(self) -> bool:
        """Return ``True`` if the result contains at least one transaction."""

        return bool(self.transactions)

    def summary(self) -> str:
        """Return a human readable summary string for logging/UX."""

        count = len(self.transactions)
        account_text = f'account {self.account_id}' if self.account_id else 'no account info'
        return f'{self.job.source_path.name}: {count} transactions, {account_text}'


@dataclass(slots=True)
class FireflyTransactionSplit:
    """Single Firefly III transaction split ready for /transactions API."""

    type: str
    date: str
    amount: str
    currency_code: str
    description: str
    external_id: str
    notes: str
    error_if_duplicate_hash: bool
    internal_reference: str
    tags: list[str] = field(default_factory=list)
    source_id: int | None = None
    destination_id: int | None = None
    source_name: str | None = None
    destination_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            'type': self.type,
            'date': self.date,
            'amount': self.amount,
            'currency_code': self.currency_code,
            'description': self.description,
            'external_id': self.external_id,
            'notes': self.notes,
            'tags': self.tags,
            'error_if_duplicate_hash': self.error_if_duplicate_hash,
            'internal_reference': self.internal_reference,
        }
        if self.source_id is not None:
            payload['source_id'] = self.source_id
        if self.destination_id is not None:
            payload['destination_id'] = self.destination_id
        if self.source_name is not None:
            payload['source_name'] = self.source_name
        if self.destination_name is not None:
            payload['destination_name'] = self.destination_name
        return payload


@dataclass(slots=True)
class FireflyPayload:
    """Full Firefly III transaction payload (single-split groups)."""

    group_title: str
    error_if_duplicate_hash: bool
    apply_rules: bool
    fire_webhooks: bool
    transactions: list[FireflyTransactionSplit]

    def to_dict(self) -> dict[str, object]:
        return {
            'group_title': self.group_title,
            'error_if_duplicate_hash': self.error_if_duplicate_hash,
            'apply_rules': self.apply_rules,
            'fire_webhooks': self.fire_webhooks,
            'transactions': [split.to_dict() for split in self.transactions],
        }


@dataclass(slots=True)
class UploadedGroup:
    """Metadata about a Firefly III transaction group returned after upload."""

    group_id: int
    journals: dict[int, list[str]]
