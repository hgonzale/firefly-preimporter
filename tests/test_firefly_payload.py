from pathlib import Path

from firefly_preimporter.firefly_payload import FireflyPayloadBuilder
from firefly_preimporter.models import ProcessingJob, ProcessingResult, SourceFormat, Transaction


def _result(amount: str) -> ProcessingResult:
    job = ProcessingJob(source_path=Path('input.csv'), source_format=SourceFormat.CSV)
    txn = Transaction(transaction_id='abc', date='2025-12-05', description='Sample', amount=amount)
    return ProcessingResult(job=job, transactions=[txn])


def test_builder_with_withdrawal() -> None:
    builder = FireflyPayloadBuilder(tag='batch-tag')
    builder.add_result(_result('-10.00'), account_id='42', currency_code='USD')
    payloads = builder.to_payloads()
    assert len(payloads) == 1
    entry = payloads[0].transactions[0]
    assert entry.type == 'withdrawal'
    assert entry.amount == '10.00'
    assert entry.source_id == 42
    assert entry.destination_name == '(no name)'
    assert entry.currency_code == 'USD'
    assert entry.tags == []
    assert entry.error_if_duplicate_hash is True
    assert entry.internal_reference == 'abc'
    assert payloads[0].group_title == 'Sample'
    assert payloads[0].error_if_duplicate_hash is True
    assert payloads[0].apply_rules is True
    assert payloads[0].fire_webhooks is True


def test_builder_with_deposit() -> None:
    builder = FireflyPayloadBuilder(tag='batch-tag')
    builder.add_result(_result('15.50'), account_id='42', currency_code='USD')
    entry = builder.to_payloads()[0].transactions[0]
    assert entry.type == 'deposit'
    assert entry.destination_id == 42
    assert entry.source_name == '(no name)'
    assert entry.error_if_duplicate_hash is True


def test_builder_respects_duplicate_flag() -> None:
    builder = FireflyPayloadBuilder(tag='batch-tag', error_on_duplicate=False)
    builder.add_result(_result('1.00'), account_id='42', currency_code='USD')
    entry = builder.to_payloads()[0].transactions[0]
    assert entry.error_if_duplicate_hash is False


def test_builder_produces_deterministic_payloads() -> None:
    first = FireflyPayloadBuilder(tag='batch-tag')
    first.add_result(_result('3.25'), account_id='42', currency_code='USD')
    second = FireflyPayloadBuilder(tag='batch-tag')
    second.add_result(_result('3.25'), account_id='42', currency_code='USD')

    assert first.to_payloads()[0].to_dict() == second.to_payloads()[0].to_dict()


def test_builder_group_title_uses_sanitized_description() -> None:
    builder = FireflyPayloadBuilder(tag='batch-tag')
    job = ProcessingJob(source_path=Path('in.csv'), source_format=SourceFormat.CSV)
    txn = Transaction(transaction_id='xyz', date='2025-01-01', description='   ' * 10, amount='-5.00')
    result = ProcessingResult(job=job, transactions=[txn])
    builder.add_result(result, account_id='1', currency_code='USD')
    payload = builder.to_payloads()[0]
    assert payload.group_title == 'Imported transaction'
    split = payload.transactions[0]
    assert split.description == 'Imported transaction'
