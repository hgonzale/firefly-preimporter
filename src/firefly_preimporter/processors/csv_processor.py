"""CSV processing pipeline for Firefly Preimporter."""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from firefly_preimporter.dedup import BatchFingerprintBuilder
from firefly_preimporter.models import ProcessingJob, ProcessingResult, Transaction

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Iterable, Iterator

REQUIRED_COLUMNS = ('date', 'description', 'amount')
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    'date': (
        'date',
        'posted date',
        'posted_date',
        'posteddate',
        'transaction date',
        'transaction_date',
        'transactiondate',
    ),
    'description': ('description', 'payee', 'memo'),
    'amount': ('amount', 'transaction amount'),
}
OPTIONAL_COLUMNS: dict[str, tuple[str, ...]] = {
    'transaction_id': ('transaction id', 'transaction_id', 'reference number', 'reference', 'reference_number'),
}
DATE_FORMATS = (
    '%m/%d/%Y',  # US: 01/31/2024
    '%m/%d/%y',  # US short: 01/31/24
    '%Y-%m-%d',  # ISO: 2024-01-31
)


def normalize_date(value: str) -> str:
    """Normalize date strings from various formats to ``YYYY-MM-DD``."""

    cleaned = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    supported_examples = 'MM/DD/YYYY, MM/DD/YY, YYYY-MM-DD'
    raise ValueError(f'Unrecognized date format: {value!r}. Supported formats: {supported_examples}')


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


def detect_required_columns(header_row: list[str]) -> tuple[dict[str, int], dict[str, int]] | None:
    """Return mappings for required and optional columns or ``None`` if required columns are missing."""

    normalized = [cell.strip().lower() for cell in header_row]
    required_indexes: dict[str, int] = {}
    for column in REQUIRED_COLUMNS:
        aliases = COLUMN_ALIASES.get(column, (column,))
        match_index = next((normalized.index(alias) for alias in aliases if alias in normalized), None)
        if match_index is None:
            return None
        required_indexes[column] = match_index

    optional_indexes: dict[str, int] = {}
    for column, aliases in OPTIONAL_COLUMNS.items():
        match_index = next((normalized.index(alias) for alias in aliases if alias in normalized), None)
        if match_index is not None:
            optional_indexes[column] = match_index
    return required_indexes, optional_indexes


def iter_transactions(rows: Iterable[list[str]]) -> Iterator[Transaction]:
    """Yield normalized ``Transaction`` entries from CSV rows."""

    column_map: dict[str, int] | None = None
    optional_map: dict[str, int] = {}
    builder = BatchFingerprintBuilder()
    for row in rows:
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < len(REQUIRED_COLUMNS):
            continue

        if column_map is None:
            detection = detect_required_columns(row)
            if detection is None:
                continue
            column_map, optional_map = detection
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

        native_id: str | None = None
        if 'transaction_id' in optional_map:
            native_id = row[optional_map['transaction_id']].strip() or None

        fp = builder.add(normalized_date, normalized_amount, description, native_id=native_id)

        yield Transaction(
            transaction_id=fp.external_id,
            date=normalized_date,
            description=description,
            amount=normalized_amount,
        )

    if column_map is None:
        required = ', '.join(REQUIRED_COLUMNS)
        raise ValueError(
            f'No header row found with required columns: {required}. '
            f'Ensure CSV has headers matching or aliased to these column names.'
        )


def process_csv(job: ProcessingJob) -> ProcessingResult:
    """Process a CSV file and return a ``ProcessingResult``."""

    path = job.source_path
    transactions: list[Transaction] = []
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle)
        transactions.extend(iter_transactions(reader))
    return ProcessingResult(job=job, transactions=transactions)
