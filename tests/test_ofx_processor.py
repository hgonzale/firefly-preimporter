from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from firefly_preimporter.models import ProcessingJob, SourceFormat
from firefly_preimporter.processors import ofx_processor


def _make_job(tmp_path: Path, name: str = 'sample.ofx') -> ProcessingJob:
    target = tmp_path / name
    target.write_text('dummy', encoding='utf-8')
    return ProcessingJob(source_path=target, source_format=SourceFormat.OFX)


def test_process_ofx_uses_fitid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    job = _make_job(tmp_path)
    record = SimpleNamespace(
        dtposted=datetime(2024, 1, 1, tzinfo=UTC),
        trnamt='-20.5',
        name='Coffee',
        memo='Latte',
        fitid='ABC123',
    )

    def fake_iter(path: Path) -> Iterator[tuple[str | None, object]]:
        assert path == job.source_path
        yield '987', record

    monkeypatch.setattr(ofx_processor, '_iter_ofx_transactions', fake_iter)

    result = ofx_processor.process_ofx(job)
    assert result.account_id == '987'
    assert result.has_transactions()
    txn = result.transactions[0]
    assert txn.transaction_id == 'ABC123'
    assert txn.description == 'Coffee'
    assert txn.amount == '-20.50'
    assert txn.date == '2024-01-01'


def test_process_ofx_handles_missing_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    job = _make_job(tmp_path)
    record = SimpleNamespace(dtposted='bad', trnamt='broken', name='', memo='', fitid=None)

    def fake_iter(_path: Path) -> Iterator[tuple[str | None, object]]:
        yield None, record

    monkeypatch.setattr(ofx_processor, '_iter_ofx_transactions', fake_iter)

    result = ofx_processor.process_ofx(job)
    assert not result.transactions
    assert result.warnings  # captures formatting failure


def _make_record(*, date: datetime, amount: str, name: str, fitid: str | None) -> SimpleNamespace:
    return SimpleNamespace(dtposted=date, trnamt=amount, name=name, memo='', fitid=fitid)


def test_ofx_identical_records_without_fitid_get_distinct_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two OFX records with identical content and no fitid must get distinct IDs."""
    job = _make_job(tmp_path)
    rec = _make_record(date=datetime(2026, 1, 15, tzinfo=UTC), amount='-5.00', name='Coffee', fitid=None)

    def fake_iter(_path: Path) -> Iterator[tuple[str | None, object]]:
        yield None, rec
        yield None, rec

    monkeypatch.setattr(ofx_processor, '_iter_ofx_transactions', fake_iter)

    result = ofx_processor.process_ofx(job)
    assert len(result.transactions) == 2
    id1, id2 = result.transactions[0].transaction_id, result.transactions[1].transaction_id
    assert id1 != id2
    assert id2 == f'{id1}-2'


def test_ofx_duplicate_fitids_are_disambiguated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If the OFX source contains duplicate fitids, they are disambiguated."""
    job = _make_job(tmp_path)
    rec = _make_record(date=datetime(2026, 1, 15, tzinfo=UTC), amount='-5.00', name='Coffee', fitid='FIT001')

    def fake_iter(_path: Path) -> Iterator[tuple[str | None, object]]:
        yield None, rec
        yield None, rec

    monkeypatch.setattr(ofx_processor, '_iter_ofx_transactions', fake_iter)

    result = ofx_processor.process_ofx(job)
    assert len(result.transactions) == 2
    assert result.transactions[0].transaction_id == 'FIT001'
    assert result.transactions[1].transaction_id == 'FIT001-2'


def test_ofx_unique_records_ids_are_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Records with distinct fitids are not affected by deduplication logic."""
    job = _make_job(tmp_path)
    rec1 = _make_record(date=datetime(2026, 1, 15, tzinfo=UTC), amount='-5.00', name='Coffee', fitid='FIT001')
    rec2 = _make_record(date=datetime(2026, 1, 16, tzinfo=UTC), amount='-40.00', name='Groceries', fitid='FIT002')

    def fake_iter(_path: Path) -> Iterator[tuple[str | None, object]]:
        yield None, rec1
        yield None, rec2

    monkeypatch.setattr(ofx_processor, '_iter_ofx_transactions', fake_iter)

    result = ofx_processor.process_ofx(job)
    assert len(result.transactions) == 2
    assert result.transactions[0].transaction_id == 'FIT001'
    assert result.transactions[1].transaction_id == 'FIT002'
