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


def test_ofx_identical_records_without_fitid_get_distinct_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_iter_ofx_transactions_raises_value_error_on_malformed_header(tmp_path: Path) -> None:
    """A file whose header doesn't parse as OFX raises a clean ValueError, not a SyntaxError."""
    ofx_file = tmp_path / 'bad_header.ofx'
    ofx_file.write_bytes(b'NOT AN OFX HEADER AT ALL\r\n\r\n<OFX></OFX>')

    with pytest.raises(ValueError, match='Failed to parse OFX file'):
        list(ofx_processor._iter_ofx_transactions(ofx_file))  # pyright: ignore[reportPrivateUsage]


def test_iter_ofx_transactions_raises_value_error_on_malformed_body(tmp_path: Path) -> None:
    """A file with a valid header but unparseable tag soup raises a clean ValueError."""
    ofx_bytes = (
        b'OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n'
        b'ENCODING:USASCII\r\nCHARSET:NONE\r\nCOMPRESSION:NONE\r\n'
        b'OLDFILEUID:NONE\r\nNEWFILEUID:NONE\r\n\r\n'
        b'<OFX><TAG>value</TAG>stray tail text<NEXT>more</NEXT></OFX>'
    )
    ofx_file = tmp_path / 'bad_body.ofx'
    ofx_file.write_bytes(ofx_bytes)

    with pytest.raises(ValueError, match='Failed to parse OFX file'):
        list(ofx_processor._iter_ofx_transactions(ofx_file))  # pyright: ignore[reportPrivateUsage]


def test_iter_ofx_transactions_raises_value_error_on_empty_file(tmp_path: Path) -> None:
    """An empty OFX file raises promptly instead of hanging in ofxtools' header parser."""
    ofx_file = tmp_path / 'empty.ofx'
    ofx_file.write_bytes(b'')

    with pytest.raises(ValueError, match='Failed to parse OFX file'):
        list(ofx_processor._iter_ofx_transactions(ofx_file))  # pyright: ignore[reportPrivateUsage]


def test_iter_ofx_parses_utf8_content_declared_as_charset_1252(tmp_path: Path) -> None:
    """CHARSET:1252 header with UTF-8 body (Apple Card export bug) parses correctly."""
    # \xc3\x8f = U+00CF (Ï) in UTF-8; byte 0x8f is undefined in cp1252 and would
    # raise UnicodeDecodeError if the declared charset were used verbatim.
    ofx_bytes = (
        b'OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n'
        b'ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\n'
        b'OLDFILEUID:NONE\r\nNEWFILEUID:NONE\r\n\r\n'
        b'<OFX>'
        b'<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS>'
        b'<DTSERVER>20260101120000[0:GMT]<LANGUAGE>ENG</SONRS></SIGNONMSGSRSV1>'
        b'<BANKMSGSRSV1><STMTTRNRS><TRNUID>1001<STATUS><CODE>0<SEVERITY>INFO</STATUS>'
        b'<STMTRS><CURDEF>USD<BANKACCTFROM><BANKID>123<ACCTID>9999<ACCTTYPE>CHECKING</BANKACCTFROM>'
        b'<BANKTRANLIST><DTSTART>20260101<DTEND>20260131'
        b'<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260115120000[0:GMT]<TRNAMT>-10.00<FITID>TX001'
        b'<NAME>CAF\xc3\x8f TEST</STMTTRN>'
        b'</BANKTRANLIST><LEDGERBAL><BALAMT>100.00<DTASOF>20260131</LEDGERBAL>'
        b'</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>'
    )
    ofx_file = tmp_path / 'apple.ofx'
    ofx_file.write_bytes(ofx_bytes)

    results = list(ofx_processor._iter_ofx_transactions(ofx_file))  # pyright: ignore[reportPrivateUsage]
    assert len(results) == 1
    _, txn = results[0]
    assert txn.name == 'CAFÏ TEST'  # U+00CF = Ï
