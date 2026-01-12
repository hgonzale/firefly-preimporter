# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-01-12

### Fixed

- Transaction preview rows now truncate columns to fit the terminal width, preventing line wrapping during uploads.

## [0.2.3] - 2025-12-14

### Changed

- Firefly uploads no longer send an explicit `group_title`; Firefly III now falls back to the split description automatically, matching the UI’s behavior and avoiding redundant metadata.
- Swapped the static type checker from Pyright to ty (tox `types` now runs `ty check`).

### Fixed

- CSV ingestion now recognizes `Transaction Date` (and its snake/camel-case variants) as the primary date column, so statements that use both “Transaction Date” and “Post Date” headers import cleanly without manual edits.

## [0.2.2] - 2025-12-13

### Changed

- Firefly uploads now pass `FireflyPayload` dataclasses straight through status logging, HTTP POSTs, and duplicate checks, eliminating the intermediate dict conversions and shrinking our remaining `Any` usage.
- Firefly API tests build fixtures via typed helpers that mirror the production dataclasses, so serialization/deserialization coverage matches the runtime structures.
- Firefly payloads now reuse each transaction's (sanitized) description as the group title, which makes the batches easier to identify inside Firefly III than the old static `firefly-preimporter` label.
- Simplified CLI flags: `-u/--upload` now always targets Firefly by default, and a companion `--fidi` switch opts the run into FiDI auto-upload when needed (replacing the old positional mode argument).

### Fixed

- `-u` / `--upload` without an explicit mode (for example `firefly-preimporter -u stmt.csv`) once again defaults to Firefly uploads instead of treating the next positional argument as an invalid mode.

## [0.2.1] - 2025-12-13

### Added

- `--upload-duplicates` flag to bypass the FiDI/Firefly duplicate guards when you intentionally need to re-ingest historical transactions (it flips both the FiDI JSON `ignore_duplicate_*` switches and the Firefly payload `error_if_duplicate_hash` bit).

### Changed

- When `-u` and `-v` are combined the CLI now prints each transaction queued for upload (id, date, amount, and filename) so verbose runs expose exactly what is being sent to FiDI or Firefly.
- Firefly uploads now POST each normalized row as its own transaction (no mixed-type splits inside one request), so statements containing both withdrawals and deposits import cleanly and match Firefly III’s journal model.
- Auto-generated upload tags follow the `ff-preimporter YYYY-MM-DD @ HH:MM` format, making it obvious which tool created a batch and when it ran.
- Firefly payloads now mirror FiDI’s deduplication strategy: batch tags are applied *after* uploads via the Firefly tagging API, leaving the hashed payload identical across reruns so `error_if_duplicate_hash` can block duplicates as intended.
- Firefly upload logging now reports each transaction’s date + first 20 description characters and whether it finished or failed, instead of generic payload numbers.
- Running with `-u/--upload` no longer drops `.firefly.csv` snapshots next to the inputs; CSVs are only written when you explicitly run in normalization/export mode.
- `-u/--upload` defaults to the Firefly API path; pass `-u fidi` if you need the legacy FiDI auto-upload behaviour.

### Fixed

- Mask account numbers in CLI prompts/logs so only the final four characters are displayed, preventing accidental leakage of full bank identifiers during account selection.
- Destination/source placeholders in Firefly API payloads are no longer populated with the transaction description, preventing bogus counterparty names from appearing in Firefly III.
- Transactions without a mapped counterparty now leave the `source_name`/`destination_name` fields empty so Firefly renders them as “(no name)” instead of “(cash)”.
- Explicitly send `(no name)` as the counterparty label for anonymous deposits/withdrawals so Firefly’s UI never falls back to “(cash)”.

## [0.2.0] - 2025-12-12

### Added

- Firefly uploads: when `-u firefly` is specified, the CLI builds a Firefly III payload (withdrawal/deposit inference, batch tagging, duplicate hash guard) and POSTs it directly to `/transactions` (unless `-n` is provided).
- New `firefly_payload` helper plus accompanying tests ensure every normalized transaction can be converted into a Firefly-ready entry with consistent tagging and metadata.

### Changed

- Upload handling has been unified under `-u/--upload [fidi|firefly]` (FiDI by default); `-n/--dry-run` now only works with `-u` and skips the final POST, while `-o/--output` doubles as both the Firefly payload destination (`-u firefly`) and the per-file directory selector.
- `--output-dir` has been removed; pass a directory to `-o/--output` to fan out per-input CSVs, or a file path for single-job CSV/payload output.
- `--account-id` accepts either a Firefly numeric ID or a bank-provided account number; non-numeric values are matched to Firefly asset accounts the same way OFX-derived identifiers are resolved.
- Firefly uploads inherit FiDI’s duplicate-hash protection by default (`firefly_error_on_duplicate = true`), keeping both paths consistent.
- The `-c` shorthand for `--config` has been dropped to avoid conflicting with other short options; use the long flag (which still documents the default config path) when pointing at custom TOML files.

### Fixed

- FiDI upload and Firefly JSON export now reuse a shared cached snapshot of Firefly asset accounts (ids plus currencies) so OFX matching stays consistent and we avoid repeated API calls mid-run.
- Dry-run stdout mode once again prints the JSON preview alongside the CSV so users inspecting batches don’t miss half of the output.
- Runs that only normalize data (no `-u/--upload`) no longer try to query the Firefly API for account lookups, so having an unreachable Firefly host no longer crashes CSV-only workflows.

## [0.1.3] - 2025-12-07

### Changed

- Added structured logging so successes are logged at INFO and failures at ERROR (instead of raw prints) and skipped/bad files no longer crash the CLI.
- Account prompts now allow previewing the first few transactions (`p`) or skipping a file entirely (`s`) when choosing the upload account.
- Account selection now displays the Firefly account id alongside the friendly name and echoes the chosen account so the JSON config’s `default_account` value is unambiguous.
- When running with `-v/--verbose`, the CLI now logs both the FiDI JSON payload we send and the HTTP response body to aid debugging issues like missing imports.
- Transaction previews now show aligned columns with the transaction id included for easier inspection before uploads.
- Previews display the three most recent transactions based on their normalized dates.
- `--stdout` combined with `-n/--dry-run` now prints the JSON config preview (to stderr) so the CSV/JSON pair is fully inspectable without writing files.
- Added `install.sh`, a helper that rebuilds the project and reinstalls the uv-managed CLI even when a virtual environment is active, and documented the workflow in the README.
- Included the FiDI-required `mapping` field in generated JSON configs to satisfy the v3 schema.
- Expanded the FiDI JSON template to include all v3-required fields (`default_account` as an integer, duplicate flags, `conversion`, and `flow=file`) and force the emitted config to use the `file` flow, preventing FiDI from rejecting uploads with “enum csv” errors.
- Auto-upload now matches OFX/QFX account numbers against Firefly asset accounts so statements that embed account IDs as strings no longer fail with “account_id must be an integer value”.

## [0.1.2] - 2025-12-07

### Fixed

- Prompt for account selection on every file when auto-uploading multiple inputs instead of reusing the first choice implicitly.

### Changed

- Swapped the static type checker from mypy to Pyright (tox `types` now runs `pyright`).

## [0.1.1] - 2025-12-07

### Fixed

- Notify users when `--dry-run` skips auto-upload to avoid silent no-op.

## [0.1.0] - 2025-12-07

### Added

- Initial release with CLI pipeline (detection, processors, outputs, uploader) and tooling (tox, mypy, ruff).
