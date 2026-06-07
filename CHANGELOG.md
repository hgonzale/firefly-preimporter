# Changelog

## v0.6.1 — 2026-06-06

### Security
- Upgraded `requests` 2.32.5 → 2.34.2, `urllib3` 2.6.0 → 2.7.0, `idna` 3.11 → 3.18,
  `pytest` 9.0.2 → 9.0.3, `filelock` 3.20.0 → 3.29.1, `pygments` 2.19.2 → 2.20.0,
  `uv` 0.9.16 → 0.11.19, `virtualenv` 20.35.4 → 21.4.2 to address Dependabot alerts.

## v0.6.0 — 2026-06-06

### Added
- Near-duplicate transaction detection: transactions with the same date and amount but
  slightly different descriptions (e.g. after a bank stops redacting reference IDs) are
  detected before upload using fuzzy string matching (`SequenceMatcher`, threshold 0.5).
- New `--near-duplicate-action` CLI flag (`prompt` / `skip` / `upload`; default: `prompt`).
  In prompt mode, near-duplicates are grouped and presented once per cluster with incoming
  and existing counts; the user chooses skip-all, upload-all, or new-only.
- `near_duplicate_threshold` config key under `[firefly-api]` (default: `0.5`).
- New `dedup` module owns all duplicate-detection logic: `TransactionFingerprint` dataclass,
  `BatchFingerprintBuilder` (same-batch occurrence tagging), and `CandidatePool`
  (one-to-one fuzzy matching).

### Fixed
- Full account numbers were printed in an INFO log during upload; they are now masked to
  last-four digits.
