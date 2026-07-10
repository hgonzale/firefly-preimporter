# Changelog

## v0.7.2 — 2026-07-10

### Fixed
- Pre-fetching existing Firefly transactions for near-duplicate detection no
  longer 422s for single-transaction-day files. Firefly's API requires
  `start` to be strictly before `end`; the date range is now widened by a
  day when a batch only spans a single date.

## v0.7.1 — 2026-07-10

### Fixed
- Account resolution no longer skips matching against Firefly's registered
  accounts just because a file-derived account number is all-digit (e.g. a
  credit card number). Previously this caused uploads to fail with
  "Currency for account ... not found" for numeric account numbers that had
  a matching Firefly account.
- Benign `ofxtools` warnings (e.g. `UnknownTagWarning` for QBO-only fields
  like `MCC`, `MERCHCAT`) are now routed through the OFX processor's own
  logger at debug level instead of being printed directly to stderr.

## v0.7.0 — 2026-07-10

### Added
- `.qbo` files are now recognized as OFX input, matching `.ofx`/`.qfx` handling.
- Files with unrecognized extensions are no longer rejected/skipped outright: if
  their content looks like a valid OFX header, they're detected as OFX
  automatically. Covers banks that export OFX-compatible data under unexpected
  extensions.

### Fixed
- Malformed or non-OFX file content passed to the OFX processor now raises a
  clean `ValueError` ("Failed to parse OFX file") instead of an uncaught
  `SyntaxError` from `ofxtools`.
- A zero-byte OFX/QFX/QBO file no longer hangs the CLI indefinitely.

## v0.6.3 — 2026-07-08

### Changed
- Reworked the near-duplicate prompt so it's clear the decision only applies to the
  current match group, not the whole run. Each matched existing transaction is now
  listed individually with its own description and match score (instead of one
  blended score for the group), and the header states the incoming transaction's
  date/amount and how many transactions in this batch share it.
- The default choice (pressing Enter, or scripted use with no `prompt_fn`) is now
  labeled `(default)` directly in the prompt, and skips only the matched
  transactions while uploading anything new in the group. Skipping the whole group,
  including new/unmatched transactions, is now a separate `[K] Skip all` option
  (previously this was the default/only "skip" behavior, and the old `[N]ew only`
  option covered what is now the default).

## v0.6.2 — 2026-06-14

### Fixed
- Near-duplicate detection no longer produces false positives when a deposit and a
  withdrawal for the same account share the same date and amount. Matching is now
  scoped to the same `account_id`.

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
