from pathlib import Path
from typing import cast

import pytest

from firefly_preimporter.config import CommonSettings, FidiSettings, FireflyApiSettings, FireflyPreimporterSettings
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction
from firefly_preimporter.output import build_csv_payload, build_json_config, write_output

TOKEN_PLACEHOLDER = 'sec' + 'ret'
IMPORT_PLACEHOLDER = 'tok' + 'en'

_FULL_JSON_CONFIG = {
    'date': 'Y-m-d',
    'delimiter': 'comma',
    'headers': True,
    'rules': True,
    'skip_form': True,
    'add_import_tag': True,
    'duplicate_detection_method': 'cell',
    'ignore_duplicate_lines': True,
    'ignore_duplicate_transactions': True,
    'unique_column_type': 'external-id',
    'unique_column_index': 0,
    'default_account': 0,
    'flow': 'file',
    'conversion': False,
    'mapping': [],
    'version': 3,
}


def _settings() -> FireflyPreimporterSettings:
    return FireflyPreimporterSettings(
        common=CommonSettings(
            personal_access_token=IMPORT_PLACEHOLDER,
            request_timeout=30,
        ),
        fidi=FidiSettings(
            import_secret=TOKEN_PLACEHOLDER,
            autoupload_url='https://example/fidi',
            json_config=dict(_FULL_JSON_CONFIG),
        ),
        firefly_api=FireflyApiSettings(
            api_base='https://example/firefly',
        ),
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
    assert config['default_account'] == 42
    assert config['flow'] == 'file'
    roles = cast('list[str]', config['roles'])
    assert isinstance(roles, list)
    assert config['do_mapping'] == [False] * len(roles)
    assert config['mapping'] == {}


def test_build_json_config_fidi_required_fields() -> None:
    settings = _settings()
    config = build_json_config(settings, account_id=None)

    required_keys = {
        'default_account',
        'date',
        'delimiter',
        'headers',
        'rules',
        'skip_form',
        'duplicate_detection_method',
        'ignore_duplicate_lines',
        'ignore_duplicate_transactions',
        'unique_column_type',
        'unique_column_index',
        'add_import_tag',
        'flow',
        'version',
        'roles',
        'mapping',
        'do_mapping',
        'conversion',
    }

    assert required_keys.issubset(config.keys())
    mapping = config['mapping']
    assert isinstance(mapping, dict)


def test_build_json_config_allows_duplicates() -> None:
    settings = _settings()
    config = build_json_config(settings, account_id='42', allow_duplicates=True)
    assert config['ignore_duplicate_transactions'] is False
    assert config['ignore_duplicate_lines'] is False


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


def test_build_csv_payload_requires_iterable() -> None:
    with pytest.raises(TypeError):
        build_csv_payload(123)  # type: ignore[arg-type]


def test_build_json_config_requires_settings() -> None:
    with pytest.raises(TypeError):
        build_json_config(object(), account_id=None)  # type: ignore[arg-type]


def test_write_output_requires_processing_result() -> None:
    with pytest.raises(TypeError):
        write_output(object(), output_path=None)  # type: ignore[arg-type]
