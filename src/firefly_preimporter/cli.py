"""Command-line interface for Firefly Preimporter."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from firefly_preimporter import __version__ as pkg_version
from firefly_preimporter.config import DEFAULT_CONFIG_PATH, FireflySettings, load_settings
from firefly_preimporter.detect import gather_jobs
from firefly_preimporter.firefly_api import (
    FireflyEmitter,
    fetch_asset_accounts,
    format_account_label,
    upload_firefly_payloads,
    write_firefly_payloads,
)
from firefly_preimporter.firefly_payload import FireflyPayloadBuilder
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction
from firefly_preimporter.output import build_csv_payload, build_json_config, write_output
from firefly_preimporter.processors.csv_processor import process_csv as process_csv_file
from firefly_preimporter.processors.ofx_processor import process_ofx as process_ofx_file
from firefly_preimporter.uploader import FidiUploader


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


def _get_account_currency_code(account_id: str, accounts: list[dict[str, object]]) -> str:
    for account in accounts:
        if str(account.get('id')) == str(account_id):
            attributes = account.get('attributes', {})
            if isinstance(attributes, Mapping):
                attributes_map = cast('Mapping[str, object]', attributes)
                currency = attributes_map.get('currency_code') or attributes_map.get('native_currency_code')
                if currency:
                    return str(currency)
            break
    raise ValueError(f'Currency for account {account_id} not found')


def _match_account_number(account_number: str, accounts: list[dict[str, object]]) -> str | None:
    candidate = account_number.strip()
    if not candidate:
        return None
    for account in accounts:
        attributes = account.get('attributes', {})
        if isinstance(attributes, Mapping):
            attributes_map = cast('Mapping[str, object]', attributes)
            acct_num = str(attributes_map.get('account_number') or '').strip()
            if acct_num and acct_num == candidate:
                return str(account.get('id'))
    return None


def _generate_batch_tag() -> str:
    return datetime.now().strftime('ff-preimporter %Y-%m-%d @ %H:%M')


def _format_firefly_status(split: Mapping[str, object]) -> str:
    date = str(split.get('date', '?'))
    description = str(split.get('description', '') or '')[:20]
    return f'{date} "{description}"'.strip()


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


def _make_emitter(args: argparse.Namespace) -> FireflyEmitter:
    def _emitter(message: str, *, error: bool = False, verbose_only: bool = False) -> None:
        _emit(message, args, error=error, verbose_only=verbose_only)

    return _emitter


def _truncate_preview_field(value: str, width: int) -> str:
    """Return a preview field truncated to ``width`` characters."""

    if width <= 0:
        return ''
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return f'{value[: width - 3]}...'


def _fit_preview_widths(widths: dict[str, int], max_total: int) -> dict[str, int]:
    """Shrink preview widths to fit within ``max_total`` characters."""

    adjusted = dict(widths)
    overflow = sum(adjusted.values()) - max_total
    if overflow <= 0:
        return adjusted

    shrink_order = ('desc', 'txid', 'date', 'amount')
    min_width = 4
    for key in shrink_order:
        if overflow <= 0:
            break
        current = adjusted[key]
        if current > min_width:
            reducible = current - min_width
            reduction = min(reducible, overflow)
            adjusted[key] = current - reduction
            overflow -= reduction

    if overflow > 0:
        for key in shrink_order:
            if overflow <= 0:
                break
            current = adjusted[key]
            if current > 1:
                reducible = current - 1
                reduction = min(reducible, overflow)
                adjusted[key] = current - reduction
                overflow -= reduction

    return adjusted


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
    indent = '  '
    sep = ' | '
    terminal_width = shutil.get_terminal_size(fallback=(120, 20)).columns
    max_payload_width = max(0, terminal_width - len(indent) - len(sep) * 3)
    widths = _fit_preview_widths(
        {
            'date': date_width,
            'txid': id_width,
            'desc': desc_width,
            'amount': amount_width,
        },
        max_payload_width,
    )
    line_fmt = (
        f'{indent}{{date:<{widths["date"]}}}{sep}'
        f'{{txid:<{widths["txid"]}}}{sep}'
        f'{{desc:<{widths["desc"]}}}{sep}'
        f'{{amount:>{widths["amount"]}}}'
    )

    print('Previewing first transactions:')
    header_line = line_fmt.format(
        date=_truncate_preview_field(headers[0], widths['date']),
        txid=_truncate_preview_field(headers[1], widths['txid']),
        desc=_truncate_preview_field(headers[2], widths['desc']),
        amount=_truncate_preview_field(headers[3], widths['amount']),
    )
    if terminal_width > 0:
        header_line = header_line[:terminal_width]
    print(header_line)
    for txn in preview:
        line = line_fmt.format(
            date=_truncate_preview_field(txn.date, widths['date']),
            txid=_truncate_preview_field(txn.transaction_id, widths['txid']),
            desc=_truncate_preview_field(txn.description, widths['desc']),
            amount=_truncate_preview_field(txn.amount, widths['amount']),
        )
        if terminal_width > 0:
            line = line[:terminal_width]
        print(line)


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
    *,
    require_resolution: bool = True,
) -> str | None:
    """Return the best account id candidate for the current job."""
    if result.account_id:
        if result.account_id.isdigit() or not require_resolution:
            return result.account_id
        if settings is not None:
            accounts = _get_asset_accounts(args, settings)
            matched = _match_account_number(result.account_id, accounts)
            if matched:
                return matched
        return result.account_id
    account_flag = getattr(args, 'account_id', None)
    if account_flag:
        candidate = str(account_flag)
        if candidate.isdigit() or not require_resolution:
            return candidate
        if settings is not None:
            accounts = _get_asset_accounts(args, settings)
            matched = _match_account_number(candidate, accounts)
            if matched:
                return matched
        return candidate
    if require_resolution:
        if settings is None:
            raise ValueError('Upload requires Firefly settings for account selection')
        accounts = _get_asset_accounts(args, settings)
        return _prompt_account_id(result, accounts)
    return None


def _write_and_upload(
    result: ProcessingResult,
    args: argparse.Namespace,
    uploader: FidiUploader | None,
    settings: FireflySettings | None,
    account_id: str | None,
    *,
    csv_output_path: Path | None,
    output_dir: Path | None,
    upload_to_fidi: bool,
    firefly_upload: bool,
    dry_run: bool,
) -> str:
    allow_duplicates = bool(getattr(args, 'upload_duplicates', False))
    destination: Path | None = None
    if not (upload_to_fidi or firefly_upload):
        destination = csv_output_path
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            destination = output_dir / f'{result.job.source_path.stem}.firefly.csv'
        elif destination is None:
            destination = result.job.source_path.with_name(f'{result.job.source_path.stem}.firefly.csv')
        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
    csv_payload = write_output(result, output_path=destination)
    if upload_to_fidi and dry_run and result.has_transactions():
        if settings is None or account_id is None:
            raise ValueError('FiDI upload requires Firefly settings for account selection')
        json_config = build_json_config(settings, account_id=account_id, allow_duplicates=allow_duplicates)
        if args.stdout:
            json_payload = json.dumps(json_config, indent=2, sort_keys=True)
            print('config.json (dry-run preview):', file=sys.stderr)
            print(json_payload, file=sys.stderr)
        _emit(f'Dry-run: skipped uploading {result.job.source_path.name}.', args)
    elif upload_to_fidi and uploader and result.has_transactions():
        if account_id is None:
            raise ValueError('FiDI upload requires a resolved account id')
        json_config = build_json_config(
            uploader.settings,
            account_id=account_id,
            allow_duplicates=allow_duplicates,
        )
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
    elif upload_to_fidi and not result.has_transactions():
        _emit(f'Skipping upload for {result.job.source_path.name}: no transactions found.', args, verbose_only=True)
    return csv_payload


def _resolve_output_targets(
    output_arg: str | None,
    jobs: list[ProcessingJob],
    *,
    firefly_upload: bool,
) -> tuple[Path | None, Path | None, Path | None]:
    if output_arg is None:
        return (None, None, None)
    dir_hint = output_arg.endswith(os.sep)
    output_path = Path(output_arg).expanduser()
    if firefly_upload:
        return (None, None, output_path)
    if len(jobs) == 1:
        if dir_hint or (output_path.exists() and output_path.is_dir()):
            return (None, output_path, None)
        return (output_path, None, None)
    if output_path.exists() and output_path.is_file():
        raise ValueError('--output must be a directory when processing multiple inputs')
    return (None, output_path, None)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Firefly Preimporter CLI')
    parser.add_argument('targets', nargs='+', type=Path, help='Input files or directories')
    parser.add_argument(
        '--config',
        type=Path,
        help=f'Path to configuration TOML (default: {DEFAULT_CONFIG_PATH})',
    )
    parser.add_argument('--account-id', help='Default Firefly account id for uploads (prompts if omitted)')
    parser.add_argument('-o', '--output', type=str, help='File path (single job) or directory (multi-job/per-file).')
    parser.add_argument('-u', '--upload', action='store_true', help='Upload normalized data (Firefly by default).')
    parser.add_argument(
        '--fidi',
        action='store_true',
        help='When used with -u/--upload, send the batch via FiDI auto-upload instead of Firefly.',
    )
    parser.add_argument('-n', '--dry-run', action='store_true', help='Dry-run uploads (skip the final POST).')
    parser.add_argument(
        '--upload-duplicates',
        action='store_true',
        help='Allow duplicate detection to be bypassed (FiDI + Firefly).',
    )
    parser.add_argument('--stdout', action='store_true', help='Print normalized CSV to stdout')
    parser.add_argument('-V', '--version', action='version', version=f'%(prog)s {pkg_version}')
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument('-q', '--quiet', action='store_true', help='Suppress informational output')
    verbosity.add_argument('-v', '--verbose', action='store_true', help='Print verbose progress details')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    firefly_emit = _make_emitter(args)
    config_arg = args.config
    config_path = (config_arg or DEFAULT_CONFIG_PATH).expanduser()
    allow_duplicate_uploads = bool(getattr(args, 'upload_duplicates', False))

    def _load(*, optional: bool) -> FireflySettings | None:
        target_path = config_arg if config_arg else None
        try:
            return load_settings(target_path)
        except FileNotFoundError:
            if optional:
                return None
            raise

    settings: FireflySettings | None = None
    if config_arg or args.upload:
        settings = _load(optional=False)
    elif config_path.is_file():
        settings = _load(optional=True)

    if args.fidi and not args.upload:
        raise ValueError('--fidi requires --upload/-u')

    upload_mode: str | None = None
    if args.upload:
        upload_mode = 'fidi' if args.fidi else 'firefly'
    elif settings and settings.default_upload:
        upload_mode = settings.default_upload

    upload_requested = upload_mode is not None
    fidi_upload = upload_mode == 'fidi'
    firefly_upload = upload_mode == 'firefly'
    firefly_payload_requested = firefly_upload
    if args.dry_run and not upload_requested:
        raise ValueError('--dry-run requires --upload/ -u')
    if upload_requested and settings is None:
        settings = _load(optional=False)
    uploader = FidiUploader(settings, dry_run=args.dry_run) if settings and fidi_upload and not args.dry_run else None
    payload_builder: FireflyPayloadBuilder | None = None
    if firefly_payload_requested:
        if settings is None:
            raise ValueError('Firefly uploads require Firefly settings for account metadata')
        payload_builder = FireflyPayloadBuilder(
            _generate_batch_tag(),
            error_on_duplicate=settings.firefly_error_on_duplicate and not allow_duplicate_uploads,
        )
    csv_output_path = args.output if not firefly_upload else None
    payload_output_path = args.output if firefly_upload else None
    jobs = gather_jobs(args.targets)
    csv_output_path, output_dir, payload_output_path = _resolve_output_targets(
        args.output,
        jobs,
        firefly_upload=firefly_upload,
    )
    if args.stdout and len(jobs) != 1:
        raise ValueError('--stdout can only be used when a single job is specified')
    if args.stdout and (csv_output_path or output_dir):
        raise ValueError('--stdout is incompatible with --output')
    combined_transactions: list[Transaction] = []
    stdout_payload: str | None = None
    require_account_resolution = upload_requested
    for job in jobs:
        try:
            result = _process_job(job)
        except Exception as exc:  # noqa: BLE001 - defensive logging
            _emit(f'Error processing {job.source_path}: {exc}', args, error=True)
            continue
        try:
            combined_transactions.extend(result.transactions)
            _emit(result.summary(), args)
            if args.verbose and upload_requested:
                for txn in result.transactions:
                    _emit(
                        (
                            f'Uploading transaction {txn.transaction_id} '
                            f'({txn.date}, {txn.amount}) from {result.job.source_path.name}'
                        ),
                        args,
                    )
            for warning in result.warnings:
                _emit(f'Warning: {warning}', args, error=True)
            account_id: str | None = None
            if settings is not None:
                account_id = _resolve_account_id(
                    result,
                    args,
                    settings,
                    require_resolution=require_account_resolution,
                )
            elif getattr(args, 'account_id', None):
                account_id = str(args.account_id)
            if payload_builder and account_id and settings is not None:
                currency_code = _get_account_currency_code(account_id, _get_asset_accounts(args, settings))
                payload_builder.add_result(result, account_id=account_id, currency_code=currency_code)
            payload = _write_and_upload(
                result,
                args,
                uploader,
                settings,
                account_id,
                csv_output_path=csv_output_path,
                output_dir=output_dir,
                upload_to_fidi=fidi_upload,
                firefly_upload=firefly_upload,
                dry_run=args.dry_run,
            )
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
    if payload_builder and payload_builder.has_payloads():
        payloads = payload_builder.to_payloads()
        if settings is None:
            raise ValueError('Firefly uploads require Firefly settings')
        if payload_output_path:
            write_firefly_payloads(payloads, payload_output_path, emit=firefly_emit)
        if firefly_upload:
            if args.dry_run:
                firefly_emit('Dry-run: skipped Firefly API upload.')
            else:
                upload_exit = upload_firefly_payloads(
                    payloads,
                    settings,
                    emit=firefly_emit,
                    batch_tag=payload_builder.tag,
                )
                if upload_exit != 0:
                    return upload_exit
    elif firefly_upload:
        firefly_emit('No transactions available for Firefly upload.', error=True)
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
