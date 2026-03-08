from pathlib import Path

import pytest

from firefly_preimporter.models import ProcessingJob, SourceFormat
from firefly_preimporter.processors.csv_processor import (
    generate_transaction_id,
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

    with pytest.raises(ValueError, match='No header row found'):
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
    with pytest.raises(ValueError, match='Unrecognized date format'):
        normalize_date('31/31/2024')


def test_normalize_date_us_format_4_digit_year() -> None:
    """Test US format with 4-digit year: MM/DD/YYYY."""
    assert normalize_date('01/31/2024') == '2024-01-31'
    assert normalize_date('12/25/2023') == '2023-12-25'
    assert normalize_date('3/5/2022') == '2022-03-05'  # Single digits


def test_normalize_date_us_format_2_digit_year() -> None:
    """Test US format with 2-digit year: MM/DD/YY."""
    assert normalize_date('01/31/24') == '2024-01-31'
    assert normalize_date('12/25/23') == '2023-12-25'
    assert normalize_date('10/10/10') == '2010-10-10'  # Ambiguous but consistent


def test_normalize_date_iso_format() -> None:
    """Test ISO 8601 format: YYYY-MM-DD."""
    assert normalize_date('2024-01-31') == '2024-01-31'
    assert normalize_date('2023-12-25') == '2023-12-25'
    assert normalize_date('2022-03-05') == '2022-03-05'


def test_normalize_date_rejects_european_formats() -> None:
    """Test that European date formats are properly rejected to avoid ambiguity."""
    # DD/MM/YYYY format should be rejected
    with pytest.raises(ValueError, match='Unrecognized date format'):
        normalize_date('31/12/2024')  # December 31, 2024 in EU format

    # DD/MM/YY format should be rejected
    with pytest.raises(ValueError, match='Unrecognized date format'):
        normalize_date('31/12/24')  # December 31, 2024 in EU short format

    # DD-MM-YYYY format should be rejected
    with pytest.raises(ValueError, match='Unrecognized date format'):
        normalize_date('31-12-2024')

    # DD.MM.YYYY format should be rejected
    with pytest.raises(ValueError, match='Unrecognized date format'):
        normalize_date('31.12.2024')


def test_normalize_amount_invalid() -> None:
    with pytest.raises(ValueError, match='unrecognized amount'):
        normalize_amount('abc')


def _csv_with_rows(tmp_path: Path, rows: list[str]) -> Path:
    file_path = tmp_path / 'stmt.csv'
    file_path.write_text('date,description,amount\n' + '\n'.join(rows), encoding='utf-8')
    return file_path


def test_identical_rows_get_distinct_ids(tmp_path: Path) -> None:
    """Two rows with identical content must produce different transaction IDs."""
    f = _csv_with_rows(tmp_path, ['2026-01-15,Coffee,-5.00', '2026-01-15,Coffee,-5.00'])
    job = ProcessingJob(source_path=f, source_format=SourceFormat.CSV)
    result = process_csv(job)
    assert len(result.transactions) == 2
    id1, id2 = result.transactions[0].transaction_id, result.transactions[1].transaction_id
    assert id1 != id2
    base = generate_transaction_id('2026-01-15', 'Coffee', '-5.00')
    assert id1 == base
    assert id2 == f'{base}-2'


def test_three_identical_rows_get_distinct_ids(tmp_path: Path) -> None:
    """Three rows with identical content produce -2 and -3 suffixes."""
    row = '2026-01-15,Coffee,-5.00'
    f = _csv_with_rows(tmp_path, [row, row, row])
    job = ProcessingJob(source_path=f, source_format=SourceFormat.CSV)
    result = process_csv(job)
    assert len(result.transactions) == 3
    base = generate_transaction_id('2026-01-15', 'Coffee', '-5.00')
    assert result.transactions[0].transaction_id == base
    assert result.transactions[1].transaction_id == f'{base}-2'
    assert result.transactions[2].transaction_id == f'{base}-3'


def test_unique_rows_ids_are_unchanged(tmp_path: Path) -> None:
    """Rows with distinct content are not affected by deduplication logic."""
    f = _csv_with_rows(tmp_path, ['2026-01-15,Coffee,-5.00', '2026-01-16,Groceries,-40.00'])
    job = ProcessingJob(source_path=f, source_format=SourceFormat.CSV)
    result = process_csv(job)
    assert len(result.transactions) == 2
    assert result.transactions[0].transaction_id == generate_transaction_id('2026-01-15', 'Coffee', '-5.00')
    assert result.transactions[1].transaction_id == generate_transaction_id('2026-01-16', 'Groceries', '-40.00')


def test_id_generation_is_stable_across_runs(tmp_path: Path) -> None:
    """Processing the same CSV twice produces identical IDs (cross-session dedup stability)."""
    rows = ['2026-01-15,Coffee,-5.00', '2026-01-15,Coffee,-5.00', '2026-01-16,Groceries,-40.00']
    f = _csv_with_rows(tmp_path, rows)
    job = ProcessingJob(source_path=f, source_format=SourceFormat.CSV)
    ids_first = [t.transaction_id for t in process_csv(job).transactions]
    ids_second = [t.transaction_id for t in process_csv(job).transactions]
    assert ids_first == ids_second


def test_native_transaction_id_collision_disambiguated(tmp_path: Path) -> None:
    """If the CSV provides duplicate native IDs, they are also disambiguated."""
    file_path = tmp_path / 'stmt.csv'
    file_path.write_text(
        'date,description,amount,reference\n'
        '2026-01-15,Coffee,-5.00,REF001\n'
        '2026-01-15,Coffee,-5.00,REF001\n',
        encoding='utf-8',
    )
    job = ProcessingJob(source_path=file_path, source_format=SourceFormat.CSV)
    result = process_csv(job)
    assert len(result.transactions) == 2
    assert result.transactions[0].transaction_id == 'REF001'
    assert result.transactions[1].transaction_id == 'REF001-2'
