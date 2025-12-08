from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from firefly_preimporter import cli
from firefly_preimporter.config import FireflySettings
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction

SECRET_PLACEHOLDER = 'sec' + 'ret'
TOKEN_PLACEHOLDER = 'tok' + 'en'


def test_parse_args_basic() -> None:
    args = cli.parse_args(['foo.csv'])
    assert args.targets == [Path('foo.csv')]
    assert not args.auto_upload


def test_parse_args_short_flags(tmp_path: Path) -> None:
    output = tmp_path / 'out.csv'
    args = cli.parse_args(['-s', '-n', '-o', str(output), '-q', 'foo.csv'])
    assert args.auto_upload
    assert args.dry_run
    assert args.output == output
    assert args.quiet


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
    exit_code = cli.main([str(dummy_job.source_path), '--output-dir', str(output_dir)])
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
        cli._process_job(job)  # noqa: SLF001


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
        default_json_config={'flow': 'csv'},
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
            return SimpleNamespace(status_code=201)

    monkeypatch.setattr(cli, 'FidiUploader', DummyUploader)

    def fake_build_json_config(_settings: FireflySettings, *, account_id: str | None) -> dict[str, object]:
        captured['account_id'] = account_id
        return {'flow': 'csv'}

    monkeypatch.setattr(cli, 'build_json_config', fake_build_json_config)

    exit_code = cli.main([str(dummy_job.source_path), '--auto-upload'])
    assert exit_code == 0
    assert captured['account_id'] == '9001'
    assert fetch_calls['count'] == 1


def test_prompt_account_id_accepts_numeric(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    accounts: list[dict[str, object]] = [{'id': '42', 'attributes': {'name': 'Checking'}}]
    responses = iter(['', '1'])
    monkeypatch.setattr('builtins.input', lambda _prompt: next(responses))
    selected = cli._prompt_account_id(dummy_job, accounts)  # noqa: SLF001
    assert selected == '42'


def test_prompt_account_id_accepts_id(monkeypatch: pytest.MonkeyPatch, dummy_job: ProcessingJob) -> None:
    accounts: list[dict[str, object]] = [{'id': '99', 'attributes': {'name': 'Savings'}}]
    monkeypatch.setattr('builtins.input', lambda _prompt: '99')
    assert cli._prompt_account_id(dummy_job, accounts) == '99'  # noqa: SLF001


def test_resolve_account_id_prefers_result(dummy_job: ProcessingJob) -> None:
    args = Namespace(auto_upload=False)
    result = ProcessingResult(job=dummy_job, account_id='777')
    resolved = cli._resolve_account_id(result, args, None)  # noqa: SLF001
    assert resolved == '777'


def test_resolve_account_id_uses_cached(dummy_job: ProcessingJob) -> None:
    args = Namespace(auto_upload=True, cached_account_id='555')
    result = ProcessingResult(job=dummy_job, account_id=None)
    resolved = cli._resolve_account_id(result, args, None)  # noqa: SLF001
    assert resolved == '555'


def test_resolve_account_id_uses_flag(dummy_job: ProcessingJob) -> None:
    args = Namespace(auto_upload=False, account_id='444')
    result = ProcessingResult(job=dummy_job, account_id=None)
    resolved = cli._resolve_account_id(result, args, None)  # noqa: SLF001
    assert resolved == '444'


def test_main_rejects_conflicting_outputs(
    monkeypatch: pytest.MonkeyPatch,
    dummy_job: ProcessingJob,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    with pytest.raises(ValueError, match='Use either --output or --output-dir'):
        cli.main([str(tmp_path / 'file.csv'), '--output', 'out.csv', '--output-dir', str(tmp_path)])


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
    capsys: pytest.CaptureFixture[str],
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
        default_json_config={'flow': 'csv'},
    )
    monkeypatch.setattr(cli, 'gather_jobs', lambda _targets: [dummy_job])
    monkeypatch.setattr(cli, '_process_job', lambda _job: result)
    monkeypatch.setattr(cli, 'load_settings', lambda _path: firefly_settings)
    accounts = [{'id': '1', 'attributes': {'name': 'Checking'}}]
    monkeypatch.setattr(cli, 'fetch_asset_accounts', lambda _settings: accounts)
    monkeypatch.setattr(cli, '_prompt_account_id', lambda _job, _accounts: '1')
    monkeypatch.setattr(cli, 'write_output', lambda _result, *, output_path=None: 'payload')  # noqa: ARG005

    exit_code = cli.main([str(dummy_job.source_path), '--auto-upload', '--dry-run'])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert 'Dry-run: skipped uploading' in captured.out
