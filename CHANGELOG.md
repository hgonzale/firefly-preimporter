# Changelog

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
