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

# Transaction ID generation
TRANSACTION_ID_LENGTH = 15  # Truncated SHA256 hash length (15 hex chars = 60 bits)
# Note: Birthday paradox collision probability ~50% at 2^30 (~1 billion) transactions

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
    '%d/%m/%Y',  # EU: 31/01/2024
    '%Y/%m/%d',  # Alternative ISO: 2024/01/31
    '%d-%m-%Y',  # EU dash: 31-01-2024
    '%d.%m.%Y',  # EU dot: 31.01.2024
)


def normalize_date(value: str) -> str:
    """Normalize date strings from various formats to ``YYYY-MM-DD``."""

    cleaned = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    supported_examples = 'MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, DD.MM.YYYY'
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


def generate_transaction_id(date: str, description: str, amount: str) -> str:
    """Build a deterministic transaction identifier from row contents."""

    digest = hashlib.sha256(f'{date}{description}{amount}'.encode()).hexdigest()
    return digest[:TRANSACTION_ID_LENGTH]


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

        transaction_id = None
        if 'transaction_id' in optional_map:
            transaction_id = row[optional_map['transaction_id']].strip() or None

        yield Transaction(
            transaction_id=transaction_id
            if transaction_id
            else generate_transaction_id(normalized_date, description, normalized_amount),
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
