"""Command-line interface for Firefly Preimporter."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from firefly_preimporter import __version__ as pkg_version
from firefly_preimporter.config import FireflySettings, load_settings
from firefly_preimporter.detect import gather_jobs
from firefly_preimporter.firefly_api import fetch_asset_accounts, format_account_label
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction
from firefly_preimporter.output import build_csv_payload, build_json_config, write_output
from firefly_preimporter.processors.csv_processor import process_csv as process_csv_file
from firefly_preimporter.processors.ofx_processor import process_ofx as process_ofx_file
from firefly_preimporter.uploader import FidiUploader
from firefly_preimporter.firefly_payload import FireflyPayloadBuilder

from datetime import datetime

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Callable


class SkipJobError(Exception):
    """Raised when the user chooses to skip processing the current job."""


PROCESSOR_MAP: dict[SourceFormat, Callable[[ProcessingJob], ProcessingResult]] = {
    SourceFormat.CSV: process_csv_file,
    SourceFormat.OFX: process_ofx_file,
}

LOGGER = logging.getLogger('firefly_preimporter.cli')
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


def _get_asset_accounts(args: argparse.Namespace, settings: FireflySettings) -> list[dict[str, object]]:
    accounts = getattr(args, 'cached_asset_accounts', None)
    if accounts is None:
        accounts = fetch_asset_accounts(settings)
        args.cached_asset_accounts = accounts
    return accounts


def _match_account_number(account_number: str, accounts: list[dict[str, object]]) -> str | None:
    candidate = account_number.strip()
    if not candidate:
        return None
    for account in accounts:
        attributes = account.get('attributes', {})
        if isinstance(attributes, Mapping):
            acct_num = str(attributes.get('account_number') or '').strip()
            if acct_num and acct_num == candidate:
                return str(account.get('id'))
    return None


def _process_job(job: ProcessingJob) -> ProcessingResult:
    processor = PROCESSOR_MAP.get(job.source_format)
    if processor is None:
        raise ValueError(f'No processor for format: {job.source_format}')
    return processor(job)


def _emit(message: str, args: argparse.Namespace, *, verbose_only: bool = False, error: bool = False) -> None:
    """Print ``message`` honoring ``--quiet``/``--verbose`` flags."""

    if verbose_only and not args.verbose:
        return
    if args.quiet and not error:
        return
    level = logging.ERROR if error else logging.INFO
    LOGGER.log(level, message)


def _preview_transactions(result: ProcessingResult, *, limit: int = 3) -> None:
    """Print a preview of the first few transactions for the current result."""

    if not result.transactions:
        print('No transactions available for preview.')
        return

    sorted_transactions = sorted(result.transactions, key=lambda txn: txn.date)
    preview = list(reversed(sorted_transactions[-limit:]))
    headers = ('Date', 'Transaction ID', 'Description', 'Amount')
    date_width = max(len(headers[0]), *(len(txn.date) for txn in preview))
    id_width = max(len(headers[1]), *(len(txn.transaction_id) for txn in preview))
    desc_width = max(len(headers[2]), *(len(txn.description) for txn in preview))
    amount_width = max(len(headers[3]), *(len(txn.amount) for txn in preview))
    line_fmt = f'  {{date:<{date_width}}} | {{txid:<{id_width}}} | {{desc:<{desc_width}}} | {{amount:>{amount_width}}}'

    print('Previewing first transactions:')
    print(
        line_fmt.format(
            date=headers[0],
            txid=headers[1],
            desc=headers[2],
            amount=headers[3],
        ),
    )
    for txn in preview:
        print(
            line_fmt.format(
                date=txn.date,
                txid=txn.transaction_id,
                desc=txn.description,
                amount=txn.amount,
            ),
        )


def _prompt_account_id(result: ProcessingResult, accounts: list[dict[str, object]]) -> str:
    """Prompt the user to choose an account id using the fetched ``accounts`` list."""

    print('Available asset accounts:')
    for idx, account in enumerate(accounts, start=1):
        print(f'  [{idx}] {format_account_label(account)}')

    prompt = f'Select account for {result.job.source_path.name} (number/id, "p" to preview, "s" to skip): '
    while True:
        response = input(prompt).strip()
        if not response:
            continue
        lowered = response.lower()
        if lowered in {'p', 'preview'}:
            _preview_transactions(result)
            continue
        if lowered in {'s', 'skip'}:
            raise SkipJobError(f'Skipping {result.job.source_path} at user request.')
        if response.isdigit():
            selected = int(response)
            if 1 <= selected <= len(accounts):
                selection = accounts[selected - 1]
                print(f'Selected: {format_account_label(selection)}')
                return str(selection.get('id'))
        for account in accounts:
            if str(account.get('id')) == response:
                print(f'Selected: {format_account_label(account)}')
                return str(account.get('id'))
        print('Invalid selection, try again.', file=sys.stderr)


def _resolve_account_id(
    result: ProcessingResult,
    args: argparse.Namespace,
    settings: FireflySettings | None,
) -> str | None:
    """Return the best account id candidate for the current job."""
    if result.account_id:
        if result.account_id.isdigit():
            return result.account_id
        if settings is not None:
            accounts = _get_asset_accounts(args, settings)
            matched = _match_account_number(result.account_id, accounts)
            if matched:
                return matched
        return result.account_id
    account_flag = getattr(args, 'account_id', None)
    if account_flag:
        return str(account_flag)
    if args.auto_upload:
        if settings is None:
            raise ValueError('Auto-upload requires Firefly settings for account selection')
        accounts = _get_asset_accounts(args, settings)
        return _prompt_account_id(result, accounts)
    return None


def _write_and_upload(
    result: ProcessingResult,
    args: argparse.Namespace,
    uploader: FidiUploader | None,
    settings: FireflySettings | None,
) -> str:
    destination: Path | None = args.output
    if args.output_dir and destination is None:
        destination = Path(args.output_dir) / f'{result.job.source_path.stem}.firefly.csv'
    elif destination is None and not args.auto_upload:
        destination = result.job.source_path.with_name(f'{result.job.source_path.stem}.firefly.csv')
    if destination and not args.auto_upload:
        destination.parent.mkdir(parents=True, exist_ok=True)
    if args.auto_upload:
        csv_payload = write_output(result, output_path=None)
    else:
        csv_payload = write_output(result, output_path=destination)
    if args.auto_upload and args.dry_run and result.has_transactions():
        if settings is None:
            raise ValueError('Auto-upload requires Firefly settings for account selection')
        account_id = _resolve_account_id(result, args, settings)
        json_config = build_json_config(settings, account_id=account_id)
        if args.stdout:
            json_payload = json.dumps(json_config, indent=2, sort_keys=True)
            print('config.json (dry-run preview):', file=sys.stderr)
            print(json_payload, file=sys.stderr)
        _emit(f'Dry-run: skipped uploading {result.job.source_path.name}.', args)
    elif args.auto_upload and uploader and result.has_transactions():
        account_id = _resolve_account_id(result, args, uploader.settings)
        json_config = build_json_config(uploader.settings, account_id=account_id)
        config_preview = json.dumps(json_config, indent=2, sort_keys=True)
        _emit(f'FiDI config payload: {config_preview}', args, verbose_only=True)
        response = uploader.upload(csv_payload, json_config)
        _emit(f'Uploaded {result.job.source_path.name}: {response.status_code}', args)
        body_text = getattr(response, 'text', '') or ''
        snippet = body_text.strip()
        if len(snippet) > 500:
            snippet = f'{snippet[:500]}…'
        if not snippet:
            snippet = '<empty response body>'
        _emit(f'FiDI response body: {snippet}', args, verbose_only=True)
    elif args.auto_upload and not result.has_transactions():
        _emit(f'Skipping upload for {result.job.source_path.name}: no transactions found.', args, verbose_only=True)
    return csv_payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Firefly Preimporter CLI')
    parser.add_argument('targets', nargs='+', type=Path, help='Input files or directories')
    parser.add_argument('-c', '--config', type=Path, help='Path to configuration TOML')
    parser.add_argument('--account-id', help='Default Firefly account id for uploads (prompts if omitted)')
    parser.add_argument('-o', '--output', type=Path, help='Path to write the CSV output')
    parser.add_argument('--output-dir', type=Path, help='Directory to write per-job CSV outputs')
    parser.add_argument('-s', '--auto-upload', action='store_true', help='Upload the normalized CSV to FiDI')
    parser.add_argument('-n', '--dry-run', action='store_true', help='Dry-run auto upload (implies --auto-upload)')
    parser.add_argument('--stdout', action='store_true', help='Print normalized CSV to stdout')
    parser.add_argument('-V', '--version', action='version', version=f'%(prog)s {pkg_version}')
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument('-q', '--quiet', action='store_true', help='Suppress informational output')
    verbosity.add_argument('-v', '--verbose', action='store_true', help='Print verbose progress details')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        args.auto_upload = True
    settings = load_settings(args.config) if args.auto_upload else None
    uploader = FidiUploader(settings, dry_run=args.dry_run) if settings and not args.dry_run else None
    jobs = gather_jobs(args.targets)
    if args.output and len(jobs) != 1:
        raise ValueError('--output can only be used when a single job is specified')
    if args.output and args.output_dir:
        raise ValueError('Use either --output or --output-dir, not both')
    if args.stdout and len(jobs) != 1:
        raise ValueError('--stdout can only be used when a single job is specified')
    if args.stdout and (args.output or args.output_dir):
        raise ValueError('--stdout is incompatible with --output or --output-dir')
    combined_transactions: list[Transaction] = []
    stdout_payload: str | None = None
    for job in jobs:
        try:
            result = _process_job(job)
        except Exception as exc:  # noqa: BLE001 - defensive logging
            _emit(f'Error processing {job.source_path}: {exc}', args, error=True)
            continue
        try:
            combined_transactions.extend(result.transactions)
            _emit(result.summary(), args)
            for warning in result.warnings:
                _emit(f'Warning: {warning}', args, error=True)
            payload = _write_and_upload(result, args, uploader, settings)
            if args.stdout:
                stdout_payload = payload
        except SkipJobError as skip_exc:
            _emit(str(skip_exc), args)
            continue
        except Exception as exc:  # noqa: BLE001 - defensive logging
            _emit(f'Error processing {job.source_path}: {exc}', args, error=True)
            continue
    if args.stdout:
        sys.stdout.write(stdout_payload or build_csv_payload(combined_transactions))
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
