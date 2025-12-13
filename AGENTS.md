# Repository Guidelines

## Project Structure & Module Organization

- `src/firefly_preimporter/` contains the CLI (`cli.py`), processors, config helpers, Firefly/FiDI clients, and stubs (`stubs/`) for third-party packages. Keep new runtime modules under `src/firefly_preimporter/` with docstrings suitable for autodoc.
- `tests/` mirrors the source layout; add new unit tests beside the module they cover (e.g., `tests/test_firefly_api.py`).
- Tooling files live at the repo root (`pyproject.toml`, `tox.ini`, `install.sh`, `README.md`). User-specific notes belong in `dev-notes.md` (ignored in git).

## Build, Test, and Development Commands

- `uv sync` — install/update dependencies in `.venv`.
- `uv run firefly-preimporter ...` — execute the CLI using the project environment.
- `tox -e lint` — run Ruff linting/format checks.
- `tox -e format` — auto-format via Ruff (use before committing style fixes).
- `tox -e types` — Pyright type checking (Firefly stubs + `py.typed` must stay consistent).
- `tox -e py311` — full pytest suite with coverage; fails if coverage < 85%.

## Coding Style & Naming Conventions

- Python 3.11+, 4-space indentation, 120-character line limit (enforced by Ruff).
- Follow descriptive, snake_case module/function names; classes use PascalCase. Avoid mutating `__all__`.
- Every public function/class requires a meaningful docstring (Sphinx friendly). Logging via `logging` only; no bare `print()` outside user messaging.

## Testing Guidelines

- Framework: `pytest` with `pytest-cov`. Tests live in `tests/` and should be named `test_<module>.py`.
- Assertions should be precise; mock network calls (FiDI/Firefly) using `unittest.mock`.
- Before opening a PR, run `tox -e lint`, `tox -e types`, and either `tox -e py311` or targeted `uv run pytest tests/<file>.py`.

## Commit & Pull Request Guidelines

- Keep commits scoped and written in imperative mood (e.g., “Add Firefly uploader”). Reference issue IDs when relevant.
- PRs should describe the change, note any new configuration knobs, and list verification commands (lint, types, tests). Include screenshots or log snippets if the change affects CLI output or user workflows.

## Configuration & Security Tips

- Secrets (FiDI import secret, Firefly PAT) live in `~/.local/etc/firefly_import.toml`; never commit them. Use `firefly_error_on_duplicate` to control duplicate detection.
- For Firefly uploads, ensure TLS certificates (`ca_cert_path`) are configured if targeting self-hosted instances.
