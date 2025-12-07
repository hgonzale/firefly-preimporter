"""CSV processing pipeline for Firefly Preimporter."""

from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from firefly_preimporter.models import ProcessingJob, ProcessingResult, Transaction

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Iterable, Iterator
REQUIRED_COLUMNS = ('date', 'description', 'amount')
DATE_FORMATS = ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d')


def normalize_date(value: str) -> str:
    """Normalize date strings from various formats to ``YYYY-MM-DD``."""

    cleaned = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    raise ValueError(f'unrecognized date: {value!r}')


def normalize_amount(value: str) -> str:
    """Normalize amount strings into ``Decimal`` values with two decimals."""

    cleaned = value.replace(',', '').strip()
    if not cleaned:
        raise ValueError('empty amount')
    try:
        decimal_value = Decimal(cleaned)
    except InvalidOperation as exc:  # pragma: no cover - defensive programming
        raise ValueError(f'unrecognized amount: {value!r}') from exc
    quantized = decimal_value.quantize(Decimal('0.01'))
    return format(quantized, '.2f')


def generate_transaction_id(date: str, description: str, amount: str) -> str:
    """Build a deterministic transaction identifier from row contents."""

    digest = hashlib.sha256(f'{date}{description}{amount}'.encode()).hexdigest()
    return digest[:15]


def detect_required_columns(header_row: list[str]) -> dict[str, int] | None:
    """Return mapping of required column name to index, or ``None`` if missing."""

    normalized = [cell.strip().lower() for cell in header_row]
    indexes: dict[str, int] = {}
    for column in REQUIRED_COLUMNS:
        if column not in normalized:
            return None
        indexes[column] = normalized.index(column)
    return indexes


def iter_transactions(rows: Iterable[list[str]]) -> Iterator[Transaction]:
    """Yield normalized ``Transaction`` entries from CSV rows."""

    column_map: dict[str, int] | None = None
    for row in rows:
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < len(REQUIRED_COLUMNS):
            continue

        if column_map is None:
            column_map = detect_required_columns(row)
            if column_map is None:
                continue
            continue

        date_raw = row[column_map['date']].strip()
        description = row[column_map['description']].strip()
        amount_raw = row[column_map['amount']].strip()
        if not date_raw or not description or not amount_raw:
            continue

        try:
            normalized_date = normalize_date(date_raw)
            normalized_amount = normalize_amount(amount_raw)
        except ValueError:
            continue

        yield Transaction(
            transaction_id=generate_transaction_id(normalized_date, description, normalized_amount),
            date=normalized_date,
            description=description,
            amount=normalized_amount,
        )

    if column_map is None:
        raise ValueError('no header row with required columns found')


def process_csv(job: ProcessingJob) -> ProcessingResult:
    """Process a CSV file and return a ``ProcessingResult``."""

    path = job.source_path
    transactions: list[Transaction] = []
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle)
        transactions.extend(iter_transactions(reader))
    return ProcessingResult(job=job, transactions=transactions)
