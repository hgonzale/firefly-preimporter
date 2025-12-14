"""OFX/QFX processing pipeline for Firefly Preimporter."""

from __future__ import annotations

import hashlib
import warnings
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from firefly_preimporter.models import ProcessingJob, ProcessingResult, Transaction
from ofxtools.models.base import OFXSpecError
from ofxtools.Parser import OFXTree
from ofxtools.Types import OFXTypeWarning

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Iterator
    from pathlib import Path
    from typing import Protocol

    class OFXTransaction(Protocol):
        dtposted: datetime | str
        trnamt: Decimal | str
        name: str | None
        memo: str | None
        fitid: str | None


def _iter_ofx_transactions(path: Path) -> Iterator[tuple[str | None, OFXTransaction]]:
    """Yield ``(account_id, transaction)`` tuples extracted via ``ofxtools``."""

    parser = OFXTree()
    with path.open('rb') as handle:
        parser.parse(handle)

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=OFXTypeWarning)
        try:
            ofx = parser.convert()
        except OFXSpecError as exc:  # pragma: no cover - exercised via unit tests
            raise ValueError(f'Failed to parse OFX file: {path}') from exc

    for statement in getattr(ofx, 'statements', []) or []:
        account = getattr(statement, 'account', None)
        account_id = getattr(account, 'acctid', None)
        for transaction in getattr(statement, 'transactions', []) or []:
            yield (str(account_id) if account_id is not None else None, transaction)


def _format_amount(value: object) -> str:
    decimal_value = Decimal(str(value))
    quantized = decimal_value.quantize(Decimal('0.01'))
    return format(quantized, '.2f')


def _format_date(value: object) -> str:
    if isinstance(value, datetime):
        moment = value.astimezone(UTC) if value.tzinfo else value
        return moment.date().isoformat()
    text = str(value)
    # Fallback for "YYYYMMDD" style values
    try:
        parsed = datetime.strptime(text[:8], '%Y%m%d')
        return parsed.date().isoformat()
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f'Unsupported OFX date value: {value!r}') from exc


def _transaction_id(date: str, description: str, amount: str, fallback: str | None) -> str:
    if fallback:
        return fallback
    digest = hashlib.sha256(f'{date}{description}{amount}'.encode()).hexdigest()
    return digest[:15]


def process_ofx(job: ProcessingJob) -> ProcessingResult:
    """Process an OFX/QFX file and return a ``ProcessingResult``."""

    path = job.source_path
    transactions: list[Transaction] = []
    warnings_list: list[str] = []
    account_id: str | None = None

    for acct_id, record in _iter_ofx_transactions(path):
        account_id = account_id or acct_id
        primary_description = getattr(record, 'name', '') or getattr(record, 'memo', '')
        description = primary_description.strip() or 'Transaction'
        dtposted = getattr(record, 'dtposted', None)
        trnamt = getattr(record, 'trnamt', None)
        if dtposted is None or trnamt is None:
            warnings_list.append('Skipping transaction with missing date or amount.')
            continue
        try:
            date_value = _format_date(dtposted)
            amount_value = _format_amount(trnamt)
        except (ValueError, InvalidOperation) as exc:
            warnings_list.append(str(exc))
            continue
        fitid = record.fitid if hasattr(record, 'fitid') else None
        txn = Transaction(
            transaction_id=_transaction_id(date_value, description, amount_value, fitid),
            date=date_value,
            description=description,
            amount=amount_value,
        )
        transactions.append(txn)

    return ProcessingResult(job=job, transactions=transactions, account_id=account_id, warnings=warnings_list)
