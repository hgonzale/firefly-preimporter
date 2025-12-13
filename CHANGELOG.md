# Changelog

All notable changes to this project will be documented in this file.

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
