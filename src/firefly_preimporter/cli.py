"""Command-line interface for Firefly Preimporter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from firefly_preimporter.config import FireflySettings, load_settings
from firefly_preimporter.detect import gather_jobs
from firefly_preimporter.firefly_api import fetch_asset_accounts, format_account_label
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction
from firefly_preimporter.output import build_csv_payload, build_json_config, write_output
from firefly_preimporter.processors.csv_processor import process_csv as process_csv_file
from firefly_preimporter.processors.ofx_processor import process_ofx as process_ofx_file
from firefly_preimporter.uploader import FidiUploader

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Callable

PROCESSOR_MAP: dict[SourceFormat, Callable[[ProcessingJob], ProcessingResult]] = {
    SourceFormat.CSV: process_csv_file,
    SourceFormat.OFX: process_ofx_file,
}


def _process_job(job: ProcessingJob) -> ProcessingResult:
    processor = PROCESSOR_MAP.get(job.source_format)
    if processor is None:
        raise ValueError(f'No processor for format: {job.source_format}')
    return processor(job)


def _emit(message: str, args: argparse.Namespace, *, verbose_only: bool = False, error: bool = False) -> None:
    """Print ``message`` honoring ``--quiet``/``--verbose`` flags."""

    if args.quiet:
        return
    if verbose_only and not args.verbose:
        return
    stream = sys.stderr if error else sys.stdout
    print(message, file=stream)


def _prompt_account_id(job: ProcessingJob, accounts: list[dict[str, object]]) -> str:
    """Prompt the user to choose an account id using the fetched ``accounts`` list."""

    print('Available asset accounts:')
    for idx, account in enumerate(accounts, start=1):
        print(f'  [{idx}] {format_account_label(account)}')

    prompt = f'Select account for {job.source_path.name} (number or Firefly id): '
    while True:
        response = input(prompt).strip()
        if not response:
            continue
        if response.isdigit():
            selected = int(response)
            if 1 <= selected <= len(accounts):
                return str(accounts[selected - 1].get('id'))
        for account in accounts:
            if str(account.get('id')) == response:
                return str(account.get('id'))
        print('Invalid selection, try again.', file=sys.stderr)


def _resolve_account_id(
    result: ProcessingResult,
    args: argparse.Namespace,
    settings: FireflySettings | None,
) -> str | None:
    """Return the best account id candidate for the current job."""

    if result.account_id:
        return result.account_id

    cached = getattr(args, 'cached_account_id', None)
    if cached:
        return cached

    if args.account_id:
        args.cached_account_id = args.account_id
        return args.account_id

    if args.auto_upload:
        if settings is None:
            raise ValueError('Auto-upload requires Firefly settings for account selection')
        accounts = getattr(args, 'cached_asset_accounts', None)
        if accounts is None:
            accounts = fetch_asset_accounts(settings)
            args.cached_asset_accounts = accounts
        chosen = _prompt_account_id(result.job, accounts)
        args.cached_account_id = chosen
        return chosen

    return None


def _write_and_upload(result: ProcessingResult, args: argparse.Namespace, uploader: FidiUploader | None) -> str:
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
    if args.auto_upload and uploader and result.has_transactions():
        account_id = _resolve_account_id(result, args, uploader.settings)
        json_config = build_json_config(uploader.settings, account_id=account_id)
        response = uploader.upload(csv_payload, json_config)
        _emit(f'Uploaded {result.job.source_path.name}: {response.status_code}', args)
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
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument('-q', '--quiet', action='store_true', help='Suppress informational output')
    verbosity.add_argument('-v', '--verbose', action='store_true', help='Print verbose progress details')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        args.auto_upload = True

    settings = load_settings(args.config) if args.auto_upload else None
    uploader = FidiUploader(settings, dry_run=args.dry_run) if settings else None

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
        result = _process_job(job)
        combined_transactions.extend(result.transactions)
        _emit(result.summary(), args)
        for warning in result.warnings:
            _emit(f'Warning: {warning}', args, error=True)
        payload = _write_and_upload(result, args, uploader)
        if args.stdout:
            stdout_payload = payload

    if args.stdout:
        sys.stdout.write(stdout_payload or build_csv_payload(combined_transactions))

    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
