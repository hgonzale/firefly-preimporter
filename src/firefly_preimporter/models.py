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
