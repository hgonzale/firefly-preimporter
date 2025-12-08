# Changelog

All notable changes to this project will be documented in this file.

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
