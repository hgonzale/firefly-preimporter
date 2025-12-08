# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2025-12-07

### Fixed

- Notify users when `--dry-run` skips auto-upload to avoid silent no-op.

### Changed

- Swapped the static type checker from mypy to Pyright (tox `types` now runs `pyright`).

## [0.1.0] - 2025-12-07

### Added

- Initial release with CLI pipeline (detection, processors, outputs, uploader) and tooling (tox, mypy, ruff).
