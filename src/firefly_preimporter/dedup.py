"""Duplicate detection utilities for Firefly Preimporter."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from firefly_preimporter.models import FireflyTransactionSplit

_TRANSACTION_ID_LENGTH = 15


@dataclass(frozen=True, slots=True)
class TransactionFingerprint:
    """All fields needed to make a duplicate-detection decision."""

    external_id: str
    date: str         # YYYY-MM-DD
    amount: str       # positive, "%.2f"
    description: str


def compute_external_id(date: str, amount: str, description: str) -> str:
    """Compute the base external ID for a transaction (without batch-occurrence suffix)."""

    digest = hashlib.sha256(f'{date}{description}{amount}'.encode()).hexdigest()
    return digest[:_TRANSACTION_ID_LENGTH]


class BatchFingerprintBuilder:
    """Stateful builder for a single CSV ingestion batch.

    Tracks occurrence counts so identical transactions within the same file
    receive distinct external IDs via a ``-2``, ``-3`` suffix.
    """

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def add(
        self,
        date: str,
        amount: str,
        description: str,
        *,
        native_id: str | None = None,
    ) -> TransactionFingerprint:
        """Build a fingerprint for one row, appending an occurrence suffix if needed.

        If ``native_id`` is provided it is used as the base ID; otherwise a hash
        of ``(date, amount, description)`` is computed.
        """

        base_id = native_id if native_id is not None else compute_external_id(date, amount, description)
        count = self._seen.get(base_id, 0) + 1
        self._seen[base_id] = count
        final_id = base_id if count == 1 else f'{base_id}-{count}'
        return TransactionFingerprint(external_id=final_id, date=date, amount=amount, description=description)


def fingerprint_from_split(split: FireflyTransactionSplit) -> TransactionFingerprint:
    """Build a ``TransactionFingerprint`` from an outgoing payload split."""

    try:
        amount = f'{float(split.amount):.2f}'
    except (ValueError, TypeError):
        amount = split.amount
    return TransactionFingerprint(
        external_id=split.external_id,
        date=split.date,
        amount=amount,
        description=split.description,
    )


def fingerprint_from_firefly(txn_map: Mapping[str, object]) -> TransactionFingerprint | None:
    """Parse a Firefly III API response transaction object into a ``TransactionFingerprint``.

    Returns ``None`` if required fields are absent or malformed.
    """

    ext_id = txn_map.get('external_id')
    if not isinstance(ext_id, str) or not ext_id:
        return None

    date_raw = txn_map.get('date')
    if not isinstance(date_raw, str) or not date_raw:
        return None
    date = date_raw[:10]

    amount_raw = txn_map.get('amount')
    if amount_raw is None:
        return None
    try:
        amount = f'{float(str(amount_raw)):.2f}'
    except (ValueError, TypeError):
        return None

    description = str(txn_map.get('description') or '').strip()

    return TransactionFingerprint(external_id=ext_id, date=date, amount=amount, description=description)


class CandidatePool:
    """One-to-one near-duplicate matching pool built from pre-fetched Firefly transactions.

    Candidates are keyed by ``(date, amount)``. Each call to ``find_near_duplicate``
    consumes the best match so the same existing transaction cannot satisfy two
    different incoming transactions.
    """

    def __init__(self, existing: list[TransactionFingerprint]) -> None:
        self._pool: dict[tuple[str, str], list[TransactionFingerprint]] = defaultdict(list)
        for fp in existing:
            self._pool[(fp.date, fp.amount)].append(fp)

    def find_near_duplicate(
        self,
        incoming: TransactionFingerprint,
        threshold: float,
    ) -> tuple[TransactionFingerprint, float] | None:
        """Return ``(match, score)`` if a near-duplicate exists above ``threshold``, else ``None``.

        The matched candidate is removed from the pool (one-to-one matching).
        """

        candidates = self._pool.get((incoming.date, incoming.amount))
        if not candidates:
            return None

        a = incoming.description.lower().strip()
        best: TransactionFingerprint | None = None
        best_score = 0.0
        for candidate in candidates:
            score = SequenceMatcher(None, a, candidate.description.lower().strip()).ratio()
            if score > best_score:
                best_score = score
                best = candidate

        if best is not None and best_score >= threshold:
            candidates.remove(best)
            return best, best_score

        return None
