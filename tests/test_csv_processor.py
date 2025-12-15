from pathlib import Path

import pytest

from firefly_preimporter.models import ProcessingJob, SourceFormat
from firefly_preimporter.processors.csv_processor import (
    normalize_amount,
    normalize_date,
    process_csv,
)


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    content = """date,description,amount
    01/01/2024,Coffee,-3.50
    2024-01-02,Deposit,1000
    03/01/24, ,5
    """
    file_path = tmp_path / 'statement.csv'
    file_path.write_text(content, encoding='utf-8')
    return file_path


def test_process_csv_returns_transactions(csv_file: Path) -> None:
    job = ProcessingJob(source_path=csv_file, source_format=SourceFormat.CSV)
    result = process_csv(job)

    assert result.job is job
    assert result.has_transactions()
    assert len(result.transactions) == 2  # skips the blank description row
    assert result.transactions[0].description == 'Coffee'
    assert result.transactions[0].amount == '-3.50'
    assert result.transactions[0].date == '2024-01-01'


def test_process_csv_missing_header(tmp_path: Path) -> None:
    file_path = tmp_path / 'bad.csv'
    file_path.write_text('no,header,here', encoding='utf-8')
    job = ProcessingJob(source_path=file_path, source_format=SourceFormat.CSV)

    with pytest.raises(ValueError, match='no header'):
        process_csv(job)


def test_process_csv_accepts_alternate_headers(tmp_path: Path) -> None:
    file_path = tmp_path / 'alt.csv'
    file_path.write_text(
        ('Posted Date,Reference Number,Payee,Address,Amount\n01/01/2024,ABC123,Electric Company,"123 Street",-45.67'),
        encoding='utf-8',
    )
    job = ProcessingJob(source_path=file_path, source_format=SourceFormat.CSV)
    result = process_csv(job)
    assert result.has_transactions()
    txn = result.transactions[0]
    assert txn.description == 'Electric Company'
    assert txn.amount == '-45.67'


def test_process_csv_supports_transaction_date_header(tmp_path: Path) -> None:
    file_path = tmp_path / 'fixture.csv'
    file_path.write_text(
        (
            'Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n'
            '11/20/2025,11/23/2025,AMYS DRIVE THRU - SFO 110,Food & Drink,Sale,-16.93,\n'
            '11/15/2025,11/16/2025,HYATT REGENCY SF ARP-PRK,Travel,Sale,-12.00,\n'
        ),
        encoding='utf-8',
    )
    job = ProcessingJob(source_path=file_path, source_format=SourceFormat.CSV)
    result = process_csv(job)
    assert len(result.transactions) == 2
    assert result.transactions[0].date == '2025-11-20'
    assert result.transactions[1].date == '2025-11-15'


def test_normalize_date_invalid() -> None:
    with pytest.raises(ValueError, match='unrecognized date'):
        normalize_date('31/31/2024')


def test_normalize_amount_invalid() -> None:
    with pytest.raises(ValueError, match='unrecognized amount'):
        normalize_amount('abc')
