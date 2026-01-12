import json
import logging
import os
from argparse import Namespace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from firefly_preimporter import cli, firefly_api
from firefly_preimporter.config import FireflySettings
from firefly_preimporter.firefly_payload import FireflyPayload
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction

SECRET_PLACEHOLDER = 'sec' + 'ret'
TOKEN_PLACEHOLDER = 'tok' + 'en'


def test_parse_args_basic() -> None:
    args = cli.parse_args(['foo.csv'])
    assert args.targets == [Path('foo.csv')]
    assert args.upload is False
    assert args.fidi is False


def test_parse_args_short_flags(tmp_path: Path) -> None:
    output = tmp_path / 'out.csv'
    args = cli.parse_args(['-u', '-n', '-o', str(output), '-q', 'foo.csv'])
    assert args.upload is True
    assert args.dry_run
    assert Path(args.output) == output
    assert args.quiet


def test_parse_args_upload_without_explicit_mode(tmp_path: Path) -> None:
    target = tmp_path / 'stmt.csv'
    args = cli.parse_args(['-u', str(target)])
    assert args.upload is True
    assert args.fidi is False
    assert args.targets == [target]


def test_parse_args_upload_long_flag_without_mode(tmp_path: Path) -> None:
    target = tmp_path / 'stmt.csv'
    args = cli.parse_args(['--upload', str(target)])
    assert args.upload is True
    assert args.fidi is False
    assert args.targets == [target]


def test_parse_args_fidi_flag_requires_upload(tmp_path: Path) -> None:
    target = tmp_path / 'stmt.csv'
    target.write_text('', encoding='utf-8')
    with pytest.raises(ValueError, match='--fidi requires --upload'):
        cli.main(['--fidi', str(target)])


@pytest.fixture
def dummy_job(tmp_path: Path) -> ProcessingJob:
    file_path = tmp_path / 'input.csv'
    file_path.write_text('transaction_id,date,description,amount\n', encoding='utf-8')
    return ProcessingJob(source_path=file_path, source_format=SourceFormat.CSV)


def test_main_writes_stdout(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)

    def fake_stdout_write_output(_result: ProcessingResult, *, output_path: Path | str | None = None) -> str:
        _ = output_path
        return 'payload'

    monkeypatch.setattr(cli, 'write_output', fake_stdout_write_output)
    monkeypatch.setattr(cli, 'build_csv_payload', lambda _txns: 'payload')
    exit_code = cli.main(['file.csv', '--stdout'])
    assert exit_code == 0
    assert 'payload' in capsys.readouterr().out


def test_main_requires_single_job_for_stdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    job_a = ProcessingJob(source_path=tmp_path / 'a.csv', source_format=SourceFormat.CSV)
    job_b = ProcessingJob(source_path=tmp_path / 'b.csv', source_format=SourceFormat.CSV)
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [job_a, job_b])

    with pytest.raises(ValueError, match='--stdout can only be used'):
        cli.main(['a.csv', 'b.csv', '--stdout'])


def test_main_respects_output_dir(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / 'outputs'
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    recorded: dict[str, Path | None] = {}

    def fake_write_output(_result: ProcessingResult, *, output_path: Path | str | None) -> str:
        recorded['path'] = Path(output_path) if output_path else None
        return 'payload'

    monkeypatch.setattr(cli, 'write_output', fake_write_output)
    exit_code = cli.main([str(dummy_job.source_path), '--output', f'{output_dir}{os.sep}'])
    assert exit_code == 0
    assert recorded['path'] == output_dir / f'{dummy_job.source_path.stem}.firefly.csv'


def test_main_writes_default_file(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    recorded: dict[str, Path | None] = {}

    def fake_write_output(_result: ProcessingResult, *, output_path: Path | str | None) -> str:
        recorded['path'] = Path(output_path) if output_path else None
        return 'payload'

    monkeypatch.setattr(cli, 'write_output', fake_write_output)
    exit_code = cli.main([str(dummy_job.source_path)])
    assert exit_code == 0
    expected = dummy_job.source_path.with_name(f'{dummy_job.source_path.stem}.firefly.csv')
    assert recorded['path'] == expected


def test_process_job_unknown_format(tmp_path: Path) -> None:
    job = ProcessingJob(source_path=tmp_path / 'weird.bin', source_format=SourceFormat.UNKNOWN)
    with pytest.raises(ValueError, match='No processor'):
        cli._process_job(job)


def test_main_requires_upload_for_dry_run(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)

    with pytest.raises(ValueError, match='--dry-run requires --upload'):
        cli.main([str(dummy_job.source_path), '--dry-run'])


def test_main_prompts_for_account(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    firefly_settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    fetch_calls = {'count': 0}

    def fake_fetch(_settings: FireflySettings) -> list[dict[str, object]]:
        fetch_calls['count'] += 1
        return [{'id': '123', 'attributes': {'name': 'Checking'}}]

    monkeypatch.setattr(cli, 'fetch_asset_accounts', fake_fetch)
    monkeypatch.setattr(cli, '_prompt_account_id', lambda _job, _accounts: '9001')

    def fake_upload_write_output(_result: ProcessingResult, *, output_path: Path | str | None = None) -> str:
        _ = output_path
        return 'payload'

    monkeypatch.setattr(cli, 'write_output', fake_upload_write_output)
    captured: dict[str, object | None] = {}

    class DummyUploader:
        def __init__(self, settings: FireflySettings, *, dry_run: bool = False) -> None:
            self.settings = settings
            self.dry_run = dry_run

        def upload(self, csv_payload: str, json_config: dict[str, object]) -> SimpleNamespace:
            captured['payload'] = csv_payload
            captured['config'] = json_config
            return SimpleNamespace(status_code=201, text='{"job":"abc"}')

    monkeypatch.setattr(cli, 'FidiUploader', DummyUploader)

    def fake_build_json_config(
        _settings: FireflySettings,
        *,
        account_id: str | None,
        allow_duplicates: bool = False,
    ) -> dict[str, object]:
        captured['account_id'] = account_id
        captured['allow_duplicates'] = allow_duplicates
        return {'flow': 'file'}

    monkeypatch.setattr(cli, 'build_json_config', fake_build_json_config)

    exit_code = cli.main([str(dummy_job.source_path), '-u', '--fidi'])
    assert exit_code == 0
    assert captured['account_id'] == '9001'
    assert fetch_calls['count'] == 1


def test_prompt_account_id_accepts_numeric(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    accounts: list[dict[str, object]] = [{'id': '42', 'attributes': {'name': 'Checking'}}]
    responses = iter(['', '1'])
    monkeypatch.setattr('builtins.input', lambda _prompt: next(responses))
    result = ProcessingResult(job=dummy_job, transactions=[])
    selected = cli._prompt_account_id(result, accounts)
    assert selected == '42'


def test_prompt_account_id_accepts_id(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    accounts: list[dict[str, object]] = [{'id': '99', 'attributes': {'name': 'Savings'}}]
    monkeypatch.setattr('builtins.input', lambda _prompt: '99')
    result = ProcessingResult(job=dummy_job, transactions=[])
    assert cli._prompt_account_id(result, accounts) == '99'


def test_prompt_account_id_adds_spacing_between_accounts(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    capsys: pytest.CaptureFixture[str],
) -> None:
    accounts: list[dict[str, object]] = [
        {'id': '1', 'attributes': {'name': 'Checking'}},
        {'id': '2', 'attributes': {'name': 'Savings'}},
    ]
    monkeypatch.setattr('builtins.input', lambda _prompt: '1')
    result = ProcessingResult(job=dummy_job, transactions=[])
    cli._prompt_account_id(result, accounts)
    output_lines = capsys.readouterr().out.splitlines()
    account_lines = [idx for idx, line in enumerate(output_lines) if line.strip().startswith('[')]
    assert len(account_lines) == 2
    assert output_lines[account_lines[0] + 1] == ''


def test_prompt_account_id_preview_command(
    monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts: list[dict[str, object]] = [{'id': '1', 'attributes': {'name': 'Checking'}}]
    responses = iter(['p', '1'])
    monkeypatch.setattr('builtins.input', lambda _prompt: next(responses))
    transactions = [
        Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50'),
        Transaction(transaction_id='2', date='2024-01-02', description='Tea', amount='-2.00'),
    ]
    result = ProcessingResult(job=dummy_job, transactions=transactions)
    selected = cli._prompt_account_id(result, accounts)
    assert selected == '1'
    output = capsys.readouterr().out
    assert 'Previewing first transactions' in output
    assert 'Coffee' in output


def test_preview_transactions_fit_terminal_width(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    capsys: pytest.CaptureFixture[str],
) -> None:
    terminal_width = 80

    def fake_terminal_size(fallback: object) -> os.terminal_size:
        _ = fallback
        return os.terminal_size((terminal_width, 20))

    monkeypatch.setattr(
        cli.shutil,
        'get_terminal_size',
        fake_terminal_size,
    )
    transactions = [
        Transaction(
            transaction_id='TX' * 20,
            date='2024-01-01',
            description='Very long description that should be truncated for preview output.',
            amount='-1234.56',
        ),
    ]
    result = ProcessingResult(job=dummy_job, transactions=transactions)
    cli._preview_transactions(result, limit=1)
    output_lines = [line for line in capsys.readouterr().out.splitlines() if ' | ' in line]
    assert output_lines
    assert all(len(line) <= terminal_width for line in output_lines)
    assert '...' in output_lines[-1]


def test_prompt_account_id_skip_command(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    accounts: list[dict[str, object]] = [{'id': '1', 'attributes': {'name': 'Checking'}}]
    monkeypatch.setattr('builtins.input', lambda _prompt: 's')
    result = ProcessingResult(job=dummy_job, transactions=[])
    with pytest.raises(cli.SkipJobError):
        cli._prompt_account_id(result, accounts)


def test_resolve_account_id_prefers_result(dummy_job: ProcessingJob) -> None:
    args = Namespace(upload=None)
    result = ProcessingResult(job=dummy_job, account_id='777')
    resolved = cli._resolve_account_id(result, args, None)
    assert resolved == '777'


def test_resolve_account_id_uses_flag(dummy_job: ProcessingJob) -> None:
    args = Namespace(upload=None, account_id='444')
    result = ProcessingResult(job=dummy_job, account_id=None)
    resolved = cli._resolve_account_id(result, args, None)
    assert resolved == '444'


def test_resolve_account_id_flag_matches_account_number(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
) -> None:
    args = Namespace(upload=True, account_id='OFX-100')
    settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    accounts: list[dict[str, object]] = [{'id': '77', 'attributes': {'name': 'Card', 'account_number': 'OFX-100'}}]
    monkeypatch.setattr(cli, 'fetch_asset_accounts', lambda _settings: accounts)
    result = ProcessingResult(job=dummy_job, account_id=None)
    resolved = cli._resolve_account_id(result, args, settings)
    assert resolved == '77'


def test_resolve_account_id_flag_returns_string_without_settings(dummy_job: ProcessingJob) -> None:
    args = Namespace(upload=None, account_id='OFX-200')
    result = ProcessingResult(job=dummy_job, account_id=None)
    resolved = cli._resolve_account_id(result, args, None)
    assert resolved == 'OFX-200'


def test_resolve_account_id_skips_lookup_when_not_uploading(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
) -> None:
    args = Namespace(upload=None)
    settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )

    def fail_fetch(_settings: FireflySettings) -> list[dict[str, object]]:  # pragma: no cover - should not run
        raise AssertionError('fetch_asset_accounts should not be called')

    monkeypatch.setattr(cli, 'fetch_asset_accounts', fail_fetch)
    result = ProcessingResult(job=dummy_job, account_id='OFX-LOOKUP')
    resolved = cli._resolve_account_id(
        result,
        args,
        settings,
        require_resolution=False,
    )
    assert resolved == 'OFX-LOOKUP'


def test_resolve_account_id_matches_account_number(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    args = Namespace(upload=True)
    settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    accounts: list[dict[str, object]] = [{'id': '55', 'attributes': {'name': 'Match', 'account_number': 'OFX-999'}}]
    monkeypatch.setattr(cli, 'fetch_asset_accounts', lambda _settings: accounts)
    result = ProcessingResult(job=dummy_job, account_id='OFX-999')
    resolved = cli._resolve_account_id(result, args, settings)
    assert resolved == '55'


def test_resolve_account_id_prompts_each_job(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    args = Namespace(upload=True)
    settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    accounts: list[dict[str, object]] = [{'id': '1', 'attributes': {'name': 'Checking'}}]
    monkeypatch.setattr(cli, 'fetch_asset_accounts', lambda _settings: accounts)
    prompt_calls = {'count': 0}

    def fake_prompt(_job: ProcessingJob, _accounts: list[dict[str, object]]) -> str:
        prompt_calls['count'] += 1
        return f'id-{prompt_calls["count"]}'

    monkeypatch.setattr(cli, '_prompt_account_id', fake_prompt)
    result = ProcessingResult(job=dummy_job, account_id=None)

    first = cli._resolve_account_id(result, args, settings)
    second = cli._resolve_account_id(result, args, settings)

    assert prompt_calls['count'] == 2
    assert first == 'id-1'
    assert second == 'id-2'


def test_main_rejects_stdout_with_output(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    with pytest.raises(ValueError, match='--stdout is incompatible'):
        cli.main([str(tmp_path / 'file.csv'), '--stdout', '--output', 'out.csv'])


def test_main_reports_dry_run_upload(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    firefly_settings = FireflySettings(
        fidi_import_secret='sec',  # noqa: S106 - test secret
        personal_access_token='tok',  # noqa: S106 - test token
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    accounts = cast('list[dict[str, object]]', [{'id': '1', 'attributes': {'name': 'Checking'}}])
    fetch_calls = {'count': 0}

    def fake_fetch(_settings: FireflySettings) -> list[dict[str, object]]:
        fetch_calls['count'] += 1
        return accounts

    monkeypatch.setattr(cli, 'fetch_asset_accounts', fake_fetch)
    monkeypatch.setattr(cli, '_prompt_account_id', lambda _job, _accounts: '1')
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'payload')  # noqa: ARG005

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    cli.LOGGER.addHandler(handler)
    try:
        exit_code = cli.main([str(dummy_job.source_path), '-u', '--fidi', '--dry-run'])
    finally:
        cli.LOGGER.removeHandler(handler)
    assert exit_code == 0
    assert 'Dry-run: skipped uploading' in log_stream.getvalue()
    assert fetch_calls['count'] == 1


def test_fidi_upload_logs_response_body_when_verbose(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    settings = FireflySettings(
        fidi_import_secret='sec',  # noqa: S106 - test secret
        personal_access_token='tok',  # noqa: S106 - test token
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: settings)
    monkeypatch.setattr(cli, '_resolve_account_id', lambda *_args, **_kwargs: '123')

    def fake_write_output(_result: ProcessingResult, *, output_path: Path | str | None = None) -> str:
        assert output_path is None
        return 'csv-data'

    monkeypatch.setattr(cli, 'write_output', fake_write_output)

    class DummyUploader:
        def __init__(self, settings: FireflySettings, *, dry_run: bool = False) -> None:
            self.settings = settings
            self.dry_run = dry_run

        def upload(self, _csv_payload: str, _json_config: dict[str, object]) -> SimpleNamespace:
            return SimpleNamespace(status_code=200, text='{"job":"123"}')

    monkeypatch.setattr(cli, 'FidiUploader', DummyUploader)

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    cli.LOGGER.addHandler(handler)
    try:
        exit_code = cli.main([str(dummy_job.source_path), '-u', '--fidi', '--verbose'])
    finally:
        cli.LOGGER.removeHandler(handler)
    assert exit_code == 0
    log_text = log_stream.getvalue()
    assert 'FiDI config payload:' in log_text
    assert '"default_account": 123' in log_text
    assert 'FiDI response body: {"job":"123"}' in log_text
    assert 'Uploading transaction 1' in log_text


def test_stdout_dry_run_prints_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_job = ProcessingJob(source_path=tmp_path / 'stmt.csv', source_format=SourceFormat.CSV)
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    firefly_settings = FireflySettings(
        fidi_import_secret='sec',  # noqa: S106 - test secret
        personal_access_token='tok',  # noqa: S106 - test token
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    monkeypatch.setattr(cli, '_resolve_account_id', lambda *_args, **_kwargs: '123')
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'csv-data')  # noqa: ARG005

    exit_code = cli.main(
        [str(dummy_job.source_path), '-u', '--fidi', '--dry-run', '--stdout'],
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == 'csv-data'
    assert '"default_account": 123' in captured.err


def test_firefly_upload_respects_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    tmp_path: Path,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    firefly_settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    monkeypatch.setattr(cli, '_resolve_account_id', lambda *_args, **_kwargs: '999')
    monkeypatch.setattr(
        cli,
        'fetch_asset_accounts',
        lambda _settings: [{'id': '999', 'attributes': {'name': 'Checking', 'currency_code': 'USD'}}],
    )
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'csv-data')  # noqa: ARG005
    payload_path = tmp_path / 'firefly.json'

    exit_code = cli.main(
        [str(dummy_job.source_path), '--upload', '--dry-run', '--output', str(payload_path)],
    )
    assert exit_code == 0
    data = json.loads(payload_path.read_text(encoding='utf-8'))
    assert isinstance(data, list)
    assert data[0]['transactions'][0]['external_id'] == '1'
    assert data[0]['transactions'][0]['error_if_duplicate_hash'] is True


@pytest.mark.parametrize('allow_duplicates', [False, True])
def test_firefly_upload_duplicate_flag_controls_builder(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    *,
    allow_duplicates: bool,
) -> None:
    firefly_settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    result = ProcessingResult(
        job=dummy_job,
        transactions=[
            Transaction(transaction_id='1', date='2024-01-01', description='Deposit', amount='100.00'),
        ],
    )
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, '_resolve_account_id', lambda *_args, **_kwargs: '1')
    monkeypatch.setattr(
        cli,
        '_get_asset_accounts',
        lambda *_args, **_kwargs: [{'id': '1', 'attributes': {'currency_code': 'USD'}}],
    )
    monkeypatch.setattr(cli, 'write_output', lambda *_args, **_kwargs: 'csv')

    recorded: dict[str, bool] = {}

    class DummyBuilder:
        def __init__(self, tag: str, *, error_on_duplicate: bool, **_kwargs: object) -> None:
            recorded['flag'] = error_on_duplicate
            self.tag = tag

        def add_result(self, *_args: object, **_kwargs: object) -> None:
            return None

        def has_payloads(self) -> bool:
            return False

        def to_payloads(self) -> list[FireflyPayload]:
            return []

    monkeypatch.setattr(cli, 'FireflyPayloadBuilder', DummyBuilder)

    args = [str(dummy_job.source_path), '--upload']
    if allow_duplicates:
        args.insert(0, '--upload-duplicates')
    exit_code = cli.main(args)
    assert exit_code == 0
    assert recorded['flag'] is (firefly_settings.firefly_error_on_duplicate and not allow_duplicates)


def test_firefly_upload_posts_payload(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    tmp_path: Path,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    firefly_settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    monkeypatch.setattr(cli, '_resolve_account_id', lambda *_args, **_kwargs: '999')
    monkeypatch.setattr(
        cli,
        'fetch_asset_accounts',
        lambda _settings: [{'id': '999', 'attributes': {'name': 'Checking', 'currency_code': 'USD'}}],
    )
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'csv-data')  # noqa: ARG005
    payload_path = tmp_path / 'firefly.json'
    captured_payloads: list[FireflyPayload] = []

    def fake_upload_firefly_payloads(
        payloads: list[FireflyPayload],
        settings: FireflySettings,
        *,
        emit: firefly_api.FireflyEmitter,
        batch_tag: str | None = None,
    ) -> int:
        captured_payloads.extend(payloads)
        _ = (settings, batch_tag)
        emit('Firefly upload 2024-01-01 "Coffee" - done')
        return 0

    monkeypatch.setattr(cli, 'upload_firefly_payloads', fake_upload_firefly_payloads)

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    cli.LOGGER.addHandler(handler)
    try:
        exit_code = cli.main([str(dummy_job.source_path), '--upload', '--output', str(payload_path)])
    finally:
        cli.LOGGER.removeHandler(handler)
    assert exit_code == 0
    assert len(captured_payloads) == 1
    payload_transactions = captured_payloads[0].transactions
    assert payload_transactions[0].external_id == '1'
    assert payload_path.exists()
    log_text = log_stream.getvalue()
    assert 'Firefly upload 2024-01-01 "Coffee" - done' in log_text
    csv_path = dummy_job.source_path.with_name(f'{dummy_job.source_path.stem}.firefly.csv')
    assert not csv_path.exists()


def test_firefly_upload_logs_response_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    firefly_settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    monkeypatch.setattr(cli, '_resolve_account_id', lambda *_args, **_kwargs: '999')
    monkeypatch.setattr(
        cli,
        'fetch_asset_accounts',
        lambda _settings: [{'id': '999', 'attributes': {'name': 'Checking', 'currency_code': 'USD'}}],
    )
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'csv-data')  # noqa: ARG005

    def fake_upload_firefly_payloads(
        payloads: list[FireflyPayload],
        settings: FireflySettings,
        *,
        emit: firefly_api.FireflyEmitter,
        batch_tag: str | None = None,
    ) -> int:
        _ = (payloads, settings, batch_tag)
        emit('Firefly upload 2024-01-01 "Coffee" - failed', error=True)
        emit('Error uploading payload to Firefly III: 422 Client Error: boom', error=True)
        emit('Firefly response body: {"message":"Invalid payload"}', error=True)
        return 1

    monkeypatch.setattr(cli, 'upload_firefly_payloads', fake_upload_firefly_payloads)

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    cli.LOGGER.addHandler(handler)
    try:
        exit_code = cli.main([str(dummy_job.source_path), '--upload'])
    finally:
        cli.LOGGER.removeHandler(handler)
    assert exit_code == 1
    log_text = log_stream.getvalue()
    assert 'Firefly upload 2024-01-01 "Coffee" - failed' in log_text
    assert 'Error uploading payload to Firefly III: 422 Client Error' in log_text
    assert 'Firefly response body: {"message":"Invalid payload"}' in log_text


def test_firefly_upload_from_config_default(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    tmp_path: Path,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    config_file = tmp_path / 'config.toml'
    config_file.write_text('dummy = true\n', encoding='utf-8')
    firefly_settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
        default_upload='firefly',
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    monkeypatch.setattr(cli, '_resolve_account_id', lambda *_args, **_kwargs: '999')
    monkeypatch.setattr(
        cli,
        'fetch_asset_accounts',
        lambda _settings: [{'id': '999', 'attributes': {'name': 'Checking', 'currency_code': 'USD'}}],
    )
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'csv-data')  # noqa: ARG005
    captured_payload: FireflyPayload | None = None

    def fake_upload_firefly_payloads(
        payloads: list[FireflyPayload],
        settings: FireflySettings,
        *,
        emit: firefly_api.FireflyEmitter,
        batch_tag: str | None = None,
    ) -> int:
        nonlocal captured_payload
        captured_payload = payloads[0]
        _ = (settings, batch_tag)
        emit('Firefly upload 2024-01-01 "Coffee" - done')
        return 0

    monkeypatch.setattr(cli, 'upload_firefly_payloads', fake_upload_firefly_payloads)

    exit_code = cli.main(
        ['--config', str(config_file), '--output', str(tmp_path / 'payload.json'), str(dummy_job.source_path)],
    )
    assert exit_code == 0
    assert captured_payload is not None
    assert captured_payload.transactions[0].external_id == '1'


def test_resolve_account_id_matches_by_account_number(tmp_path: Path) -> None:
    job = ProcessingJob(source_path=tmp_path / 'acc.csv', source_format=SourceFormat.CSV)
    result = ProcessingResult(job=job, account_id='ACCT-3550')
    args = Namespace(account_id=None)
    args.cached_asset_accounts = [{'id': '777', 'attributes': {'account_number': 'ACCT-3550'}}]
    settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )

    resolved = cli._resolve_account_id(result, args, settings, require_resolution=True)

    assert resolved == '777'


def test_main_logs_error_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bad_job = ProcessingJob(source_path=tmp_path / 'bad.csv', source_format=SourceFormat.CSV)
    good_job = ProcessingJob(source_path=tmp_path / 'good.csv', source_format=SourceFormat.CSV)
    result = ProcessingResult(
        job=good_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )

    def fake_process(job: ProcessingJob) -> ProcessingResult:
        if job is bad_job:
            raise ValueError('boom')
        return result

    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [bad_job, good_job])
    monkeypatch.setattr(cli, '_process_job', fake_process)
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'payload')  # noqa: ARG005

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    cli.LOGGER.addHandler(handler)
    try:
        exit_code = cli.main([str(tmp_path)])
    finally:
        cli.LOGGER.removeHandler(handler)
    assert exit_code == 0
    log_text = log_stream.getvalue()
    assert 'ERROR' in log_text
    assert 'boom' in log_text
    assert good_job.source_path.name in log_text


def test_main_handles_user_skip(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
) -> None:
    result = ProcessingResult(
        job=dummy_job,
        transactions=[Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50')],
    )
    settings = FireflySettings(
        fidi_import_secret=SECRET_PLACEHOLDER,
        personal_access_token=TOKEN_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/api',
        ca_cert_path=None,
        request_timeout=10,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={},
        default_json_config={'flow': 'file'},
        firefly_error_on_duplicate=True,
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: settings)
    monkeypatch.setattr(
        cli, 'fetch_asset_accounts', lambda _settings: [{'id': '1', 'attributes': {'name': 'Checking'}}]
    )

    def fake_prompt(_result: ProcessingResult, _accounts: list[dict[str, object]]) -> str:
        raise cli.SkipJobError('Skipping test file')

    monkeypatch.setattr(cli, '_prompt_account_id', fake_prompt)

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    cli.LOGGER.addHandler(handler)
    try:
        exit_code = cli.main([str(dummy_job.source_path), '-u'])
    finally:
        cli.LOGGER.removeHandler(handler)
    assert exit_code == 0
    assert 'Skipping test file' in log_stream.getvalue()
