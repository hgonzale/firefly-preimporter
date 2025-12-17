# Repository Guidelines

## Project Structure & Module Organization

- `src/firefly_preimporter/` contains the CLI (`cli.py`), processors, config helpers, Firefly/FiDI clients, and stubs (`stubs/`) for third-party packages. Keep new runtime modules under `src/firefly_preimporter/` with docstrings suitable for autodoc.
- `tests/` mirrors the source layout; add new unit tests beside the module they cover (e.g., `tests/test_firefly_api.py`).
- Tooling files live at the repo root (`pyproject.toml`, `tox.ini`, `install.sh`, `README.md`).

## Build, Test, and Development Commands

- `uv sync` — install/update dependencies in `.venv`.
- `uv run firefly-preimporter ...` — execute the CLI using the project environment.
- Activate the repo-managed environment with `source .venv/bin/activate` before running local commands (tox, pytest, etc.); do not create ad-hoc venvs.
- Never call `pip install` directly; declare dependencies in `pyproject.toml` and let `uv sync`/`uv pip` manage installs.
- `tox -e lint` — run Ruff linting/format checks.
- `tox -e format` — auto-format via Ruff (use before committing style fixes).
- `tox -e types` — ty type checking (Firefly stubs + `py.typed` must stay consistent).
- `tox -e py311` — full pytest suite with coverage; fails if coverage < 85%.

## Coding Style & Naming Conventions

- Python 3.11+, 4-space indentation, 120-character line limit (enforced by Ruff).
- Follow descriptive, snake_case module/function names; classes use PascalCase. Avoid mutating `__all__`.
- Every public function/class requires a meaningful docstring (Sphinx friendly). Logging via `logging` only; no bare `print()` outside user messaging.
- Minimize use of `Any`; prefer concrete typing (dataclasses, TypedDicts, enums) over loosely typed `dict[str, Any]`/`list[Any]` helpers so ty can enforce real contracts.
- House common dataclasses in `src/firefly_preimporter/models.py` whenever practical so types are discoverable by both runtime code and stubs/tests.

## Testing Guidelines

- Framework: `pytest` with `pytest-cov`. Tests live in `tests/` and should be named `test_<module>.py`.
- Assertions should be precise; mock network calls (FiDI/Firefly) using `unittest.mock`.
- For every task, execute the full tox pipeline (`tox -e lint`, `tox -e format`, `tox -e types`, `tox -e py311`). Use targeted `uv run pytest tests/<file>.py` only for quick iteration, but finish by re-running tox.

## Commit & Pull Request Guidelines

- Keep commits scoped and written in imperative mood (e.g., “Add Firefly uploader”). Reference issue IDs when relevant.
- PRs should describe the change, note any new configuration knobs, and list verification commands (lint, types, tests). Include screenshots or log snippets if the change affects CLI output or user workflows.
- If the change modifies user-facing behavior, tooling, or workflows, append a concise entry to `CHANGELOG.md` under the current unreleased section (match whatever version is being prepared in `pyproject.toml`).

## Configuration & Security Tips

- Secrets (FiDI import secret, Firefly PAT) live in `~/.local/etc/firefly_import.toml`; never commit them. Use `firefly_error_on_duplicate` to control duplicate detection.
- For Firefly uploads, ensure TLS certificates (`ca_cert_path`) are configured if targeting self-hosted instances.
- Treat financial account identifiers as sensitive: whenever logging or displaying account numbers, mask everything except the last four characters (the CLI already does this—match that behavior in new code or tests).
