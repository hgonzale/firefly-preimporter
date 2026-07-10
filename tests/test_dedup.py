"""Tests for firefly_preimporter.dedup."""

from __future__ import annotations

from firefly_preimporter.dedup import (
    BatchFingerprintBuilder,
    CandidatePool,
    TransactionFingerprint,
    compute_external_id,
    fingerprint_from_firefly,
    fingerprint_from_split,
)
from firefly_preimporter.models import FireflyTransactionSplit


def _fp(
    date: str = '2024-05-06',
    amount: str = '45.00',
    description: str = 'PAYMENT 123',
    external_id: str = 'abc123',
    account_id: int | None = 1,
) -> TransactionFingerprint:
    return TransactionFingerprint(
        external_id=external_id, date=date, amount=amount, description=description, account_id=account_id
    )


def _make_split(
    date: str = '2024-05-06',
    amount: str = '45.00',
    description: str = 'PAYMENT 123',
    external_id: str = 'abc123',
) -> FireflyTransactionSplit:
    return FireflyTransactionSplit(
        type='withdrawal',
        date=date,
        amount=amount,
        currency_code='USD',
        description=description,
        external_id=external_id,
        notes=description,
        error_if_duplicate_hash=True,
        internal_reference=external_id,
        source_id=1,
    )


# --- BatchFingerprintBuilder ---


def test_batch_builder_first_occurrence_no_suffix() -> None:
    builder = BatchFingerprintBuilder()
    fp = builder.add('2024-05-06', '45.00', 'PAYMENT 123')
    assert fp.external_id == compute_external_id('2024-05-06', '45.00', 'PAYMENT 123')
    assert fp.date == '2024-05-06'
    assert fp.amount == '45.00'
    assert fp.description == 'PAYMENT 123'


def test_batch_builder_second_occurrence_gets_suffix() -> None:
    builder = BatchFingerprintBuilder()
    fp1 = builder.add('2024-05-06', '45.00', 'PAYMENT 123')
    fp2 = builder.add('2024-05-06', '45.00', 'PAYMENT 123')
    base = compute_external_id('2024-05-06', '45.00', 'PAYMENT 123')
    assert fp1.external_id == base
    assert fp2.external_id == f'{base}-2'


def test_batch_builder_third_occurrence_gets_suffix() -> None:
    builder = BatchFingerprintBuilder()
    builder.add('2024-05-06', '45.00', 'PAYMENT 123')
    builder.add('2024-05-06', '45.00', 'PAYMENT 123')
    fp3 = builder.add('2024-05-06', '45.00', 'PAYMENT 123')
    base = compute_external_id('2024-05-06', '45.00', 'PAYMENT 123')
    assert fp3.external_id == f'{base}-3'


def test_batch_builder_different_transactions_independent() -> None:
    builder = BatchFingerprintBuilder()
    fp_a = builder.add('2024-05-06', '45.00', 'PAYMENT A')
    fp_b = builder.add('2024-05-06', '45.00', 'PAYMENT B')
    assert fp_a.external_id == compute_external_id('2024-05-06', '45.00', 'PAYMENT A')
    assert fp_b.external_id == compute_external_id('2024-05-06', '45.00', 'PAYMENT B')


def test_batch_builder_description_change_produces_different_base_id() -> None:
    base1 = compute_external_id('2024-05-06', '45.00', 'PAYMENT REDACTED')
    base2 = compute_external_id('2024-05-06', '45.00', 'PAYMENT 123456')
    assert base1 != base2


def test_batch_builder_native_id_no_suffix() -> None:
    builder = BatchFingerprintBuilder()
    fp = builder.add('2024-05-06', '45.00', 'PAYMENT 123', native_id='REF001')
    assert fp.external_id == 'REF001'


def test_batch_builder_native_id_collision_gets_suffix() -> None:
    builder = BatchFingerprintBuilder()
    fp1 = builder.add('2024-05-06', '45.00', 'PAYMENT 123', native_id='REF001')
    fp2 = builder.add('2024-05-06', '45.00', 'PAYMENT 456', native_id='REF001')
    assert fp1.external_id == 'REF001'
    assert fp2.external_id == 'REF001-2'


# --- fingerprint_from_split ---


def test_fingerprint_from_split_normalizes_amount() -> None:
    split = _make_split(amount='10')
    fp = fingerprint_from_split(split)
    assert fp.amount == '10.00'


def test_fingerprint_from_split_preserves_fields() -> None:
    split = _make_split(date='2024-05-06', amount='45.00', description='PAYMENT', external_id='xyz')
    fp = fingerprint_from_split(split)
    assert fp.external_id == 'xyz'
    assert fp.date == '2024-05-06'
    assert fp.description == 'PAYMENT'
    assert fp.account_id == 1  # source_id from _make_split


# --- fingerprint_from_firefly ---


def test_fingerprint_from_firefly_normalizes_iso_date() -> None:
    txn = {'external_id': 'abc', 'date': '2024-05-06T00:00:00+00:00', 'amount': '45.00', 'description': 'PAY'}
    fp = fingerprint_from_firefly(txn, account_id=7)
    assert fp is not None
    assert fp.date == '2024-05-06'
    assert fp.account_id == 7


def test_fingerprint_from_firefly_normalizes_amount() -> None:
    txn = {'external_id': 'abc', 'date': '2024-05-06', 'amount': '4.5', 'description': 'PAY'}
    fp = fingerprint_from_firefly(txn)
    assert fp is not None
    assert fp.amount == '4.50'


def test_fingerprint_from_firefly_returns_none_on_missing_external_id() -> None:
    txn = {'date': '2024-05-06', 'amount': '45.00', 'description': 'PAY'}
    assert fingerprint_from_firefly(txn) is None


def test_fingerprint_from_firefly_returns_none_on_empty_external_id() -> None:
    txn = {'external_id': '', 'date': '2024-05-06', 'amount': '45.00', 'description': 'PAY'}
    assert fingerprint_from_firefly(txn) is None


def test_fingerprint_from_firefly_returns_none_on_missing_date() -> None:
    txn = {'external_id': 'abc', 'amount': '45.00', 'description': 'PAY'}
    assert fingerprint_from_firefly(txn) is None


def test_fingerprint_from_firefly_returns_none_on_malformed_amount() -> None:
    txn = {'external_id': 'abc', 'date': '2024-05-06', 'amount': 'not-a-number', 'description': 'PAY'}
    assert fingerprint_from_firefly(txn) is None


# --- CandidatePool ---


def test_candidate_pool_finds_match_above_threshold() -> None:
    existing = [_fp(description='PAYMENT REDACTED', external_id='old')]
    pool = CandidatePool(existing)
    incoming = _fp(description='PAYMENT 123456', external_id='new')
    result = pool.find_near_duplicate(incoming, threshold=0.5)
    assert result is not None
    match, score = result
    assert match.external_id == 'old'
    assert score >= 0.5


def test_candidate_pool_returns_none_below_threshold() -> None:
    existing = [_fp(description='COMPLETELY UNRELATED TRANSACTION', external_id='old')]
    pool = CandidatePool(existing)
    incoming = _fp(description='PAYMENT 123456', external_id='new')
    assert pool.find_near_duplicate(incoming, threshold=0.95) is None


def test_candidate_pool_returns_none_for_different_date() -> None:
    existing = [_fp(date='2024-05-07', description='PAYMENT', external_id='old')]
    pool = CandidatePool(existing)
    incoming = _fp(date='2024-05-06', description='PAYMENT', external_id='new')
    assert pool.find_near_duplicate(incoming, threshold=0.5) is None


def test_candidate_pool_returns_none_for_different_amount() -> None:
    existing = [_fp(amount='50.00', description='PAYMENT', external_id='old')]
    pool = CandidatePool(existing)
    incoming = _fp(amount='45.00', description='PAYMENT', external_id='new')
    assert pool.find_near_duplicate(incoming, threshold=0.5) is None


def test_candidate_pool_one_to_one_first_match_consumed() -> None:
    existing = [_fp(description='PAYMENT REDACTED', external_id='old')]
    pool = CandidatePool(existing)
    result1 = pool.find_near_duplicate(_fp(description='PAYMENT 123456', external_id='new1'), threshold=0.5)
    result2 = pool.find_near_duplicate(_fp(description='PAYMENT 123456', external_id='new2'), threshold=0.5)
    assert result1 is not None
    assert result2 is None


def test_candidate_pool_two_existing_two_incoming_each_gets_own_match() -> None:
    existing = [
        _fp(description='PAYMENT REDACTED', external_id='old1'),
        _fp(description='PAYMENT REDACTED', external_id='old2'),
    ]
    pool = CandidatePool(existing)
    result1 = pool.find_near_duplicate(_fp(description='PAYMENT 123456', external_id='new1'), threshold=0.5)
    result2 = pool.find_near_duplicate(_fp(description='PAYMENT 123456', external_id='new2'), threshold=0.5)
    assert result1 is not None
    assert result2 is not None
    assert result1[0].external_id != result2[0].external_id


def test_candidate_pool_score_uses_lowercased_descriptions() -> None:
    existing = [_fp(description='STARBUCKS MAIN ST', external_id='old')]
    pool = CandidatePool(existing)
    incoming = _fp(description='starbucks main st', external_id='new')
    result = pool.find_near_duplicate(incoming, threshold=0.99)
    assert result is not None
    _, score = result
    assert score == 1.0


def test_candidate_pool_different_account_no_match() -> None:
    """Transactions for a different account_id must never be flagged as near-duplicates."""
    existing = [_fp(description='PAYMENT REDACTED', external_id='old', account_id=2)]
    pool = CandidatePool(existing)
    incoming = _fp(description='PAYMENT 123456', external_id='new', account_id=1)
    assert pool.find_near_duplicate(incoming, threshold=0.5) is None


def test_candidate_pool_same_account_matches() -> None:
    """Same account_id still matches when description similarity is above threshold."""
    existing = [_fp(description='PAYMENT REDACTED', external_id='old', account_id=1)]
    pool = CandidatePool(existing)
    incoming = _fp(description='PAYMENT 123456', external_id='new', account_id=1)
    result = pool.find_near_duplicate(incoming, threshold=0.5)
    assert result is not None
    assert result[0].external_id == 'old'
