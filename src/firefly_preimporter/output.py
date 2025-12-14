"""Output utilities for writing CSV/JSON payloads for FiDI."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from firefly_preimporter.config import DEFAULT_JSON_CONFIG, FireflySettings
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


def build_json_config(
    settings: FireflySettings,
    *,
    account_id: str | None,
    allow_duplicates: bool = False,
) -> dict[str, object]:
    """Construct the FiDI JSON config payload for the given account."""

    if not isinstance(settings, FireflySettings):
        raise TypeError('invalid Firefly settings')

    config = dict(DEFAULT_JSON_CONFIG)
    config.update(settings.default_json_config)
    # FiDI v3 schema restricts ``flow`` to a small enum of recognizable sources.
    # Our CLI always operates as a local file importer.
    config['flow'] = 'file'
    if account_id:
        try:
            config['default_account'] = int(account_id)
        except (TypeError, ValueError) as exc:
            raise ValueError('account_id must be an integer value') from exc
    roles = list(config.get('roles') or ['internal_reference', 'date_transaction', 'description', 'amount'])
    config['roles'] = roles

    # FiDI expects ``mapping`` to be an object (or, less commonly, an array of
    # objects) describing per-column overrides. When no mapping data exists we
    # must emit an empty object ({}), not an empty array, to satisfy FiDI's own
    # downloader/validator logic.
    raw_mapping = config.get('mapping')
    mapping: dict[str, object] = raw_mapping if isinstance(raw_mapping, dict) else {}
    config['mapping'] = mapping
    config['do_mapping'] = [False] * len(roles)
    if allow_duplicates:
        config['ignore_duplicate_lines'] = False
        config['ignore_duplicate_transactions'] = False

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
