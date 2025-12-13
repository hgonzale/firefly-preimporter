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
    payload = builder.to_dict()
    entry = payload['transactions'][0]
    assert entry['type'] == 'withdrawal'
    assert entry['amount'] == '10.00'
    assert entry['source_id'] == 42
    assert entry['currency_code'] == 'USD'
    assert entry['tags'] == ['batch-tag']
    assert entry['error_if_duplicate_hash'] is True
    assert entry['internal_reference'] == 'abc'
    assert payload['group_title'] == 'batch-tag'
    assert payload['error_if_duplicate_hash'] is True
    assert payload['apply_rules'] is True
    assert payload['fire_webhooks'] is True


def test_builder_with_deposit() -> None:
    builder = FireflyPayloadBuilder(tag='batch-tag')
    builder.add_result(_result('15.50'), account_id='42', currency_code='USD')
    entry = builder.to_dict()['transactions'][0]
    assert entry['type'] == 'deposit'
    assert entry['destination_id'] == 42
    assert entry['source_name'] == 'Sample'
    assert entry['error_if_duplicate_hash'] is True


def test_builder_respects_duplicate_flag() -> None:
    builder = FireflyPayloadBuilder(tag='batch-tag', error_on_duplicate=False)
    builder.add_result(_result('1.00'), account_id='42', currency_code='USD')
    entry = builder.to_dict()['transactions'][0]
    assert entry['error_if_duplicate_hash'] is False
