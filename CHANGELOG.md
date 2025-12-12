# Changelog

All notable changes to this project will be documented in this file.

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
