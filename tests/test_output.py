from pathlib import Path

from firefly_preimporter.config import FireflySettings
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction
from firefly_preimporter.output import build_csv_payload, build_json_config, write_output

TOKEN_PLACEHOLDER = 'sec' + 'ret'
IMPORT_PLACEHOLDER = 'tok' + 'en'


def _settings() -> FireflySettings:
    return FireflySettings(
        fidi_import_secret=TOKEN_PLACEHOLDER,
        personal_access_token=IMPORT_PLACEHOLDER,
        fidi_autoupload_url='https://example/fidi',
        firefly_api_base='https://example/firefly',
        ca_cert_path=None,
        request_timeout=30,
        unique_column_role='internal_reference',
        date_column_role='date_transaction',
        known_roles={'dtposted': 'date_transaction'},
        default_json_config={'flow': 'csv'},
    )


def test_build_csv_payload() -> None:
    transactions = [
        Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50'),
        Transaction(transaction_id='2', date='2024-01-02', description='Deposit', amount='100.00'),
    ]
    payload = build_csv_payload(transactions)
    assert 'transaction_id,date,description,amount' in payload
    assert payload.count('\n') == 3  # header + two rows


def test_build_json_config_includes_account() -> None:
    settings = _settings()
    config = build_json_config(settings, account_id='42')
    assert config['default_account'] == '42'
    assert config['flow'] == 'csv'
    roles = config['roles']
    assert isinstance(roles, list)
    assert config['do_mapping'] == [False] * len(roles)


def test_write_output_writes_file(tmp_path: Path) -> None:
    job = ProcessingJob(source_path=tmp_path / 'input.csv', source_format=SourceFormat.CSV)
    result = ProcessingResult(
        job=job,
        transactions=[
            Transaction(transaction_id='1', date='2024-01-01', description='Coffee', amount='-3.50'),
        ],
    )
    output_file = tmp_path / 'out.csv'
    csv_payload = write_output(result, output_path=output_file)
    with output_file.open('r', encoding='utf-8', newline='') as handle:
        assert handle.read() == csv_payload
