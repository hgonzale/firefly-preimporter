"""Output utilities for writing CSV/JSON payloads for FiDI."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from firefly_preimporter.config import FireflySettings
from firefly_preimporter.models import ProcessingResult, Transaction


def build_csv_payload(transactions: Iterable[Transaction]) -> str:
    """Serialize transactions into a Firefly-compatible CSV string."""

    if not isinstance(transactions, Iterable):
        raise TypeError('transactions must be iterable')

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=['transaction_id', 'date', 'description', 'amount'])
    writer.writeheader()
    for txn in transactions:
        writer.writerow(asdict(txn))
    return buffer.getvalue()


def build_json_config(settings: FireflySettings, *, account_id: str | None) -> dict[str, object]:
    """Construct the FiDI JSON config payload for the given account."""

    if not isinstance(settings, FireflySettings):
        raise TypeError('invalid Firefly settings')

    config = dict(settings.default_json_config)
    if account_id:
        config['default_account'] = account_id
    roles = list(config.get('roles') or ['internal_reference', 'date_transaction', 'description', 'amount'])
    config['roles'] = roles
    config['do_mapping'] = [False] * len(roles)
    return config


def write_output(result: ProcessingResult, *, output_path: Path | str | None) -> str:
    """Write the CSV payload to ``output_path`` if provided and return the CSV string."""

    if not isinstance(result, ProcessingResult):
        raise TypeError('invalid processing result')

    csv_payload = build_csv_payload(result.transactions)
    if output_path:
        path = Path(output_path)
        with path.open('w', encoding='utf-8', newline='') as handle:
            handle.write(csv_payload)
    return csv_payload
