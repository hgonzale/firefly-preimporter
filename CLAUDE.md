# firefly-preimporter

## Project Structure

- `src/firefly_preimporter/` — CLI (`cli.py`), config, Firefly/FiDI clients, models, and helpers.
- `stubs/` — hand-written stubs for third-party packages without type info (`ofxtools`, `requests`).
- `tests/` — mirrors source layout; name files `test_<module>.py`.
- Common dataclasses go in `models.py` so types are discoverable by both runtime code and stubs.

## Development Commands

- `uv sync` — install/update dependencies in `.venv`.
- `uv run firefly-preimporter ...` — run the CLI.
- Use `source .venv/bin/activate` before running `tox` or `pytest` directly; don't create ad-hoc venvs.
- Never `pip install`; declare deps in `pyproject.toml`.

| Command | Purpose |
|---|---|
| `tox -e lint` | Ruff lint + format check |
| `tox -e format` | Auto-fix with Ruff |
| `tox -e types` | ty type checking |
| `tox -e tests` | pytest + coverage (fails below 85%) |

Run the full pipeline after each feature or fix.

## Coding Style

- Python 3.13+, 4-space indent, 120-char line limit (enforced by Ruff).
- snake_case for functions/modules, PascalCase for classes.
- Every public function/class needs a docstring. Use `logging`, not `print()`.
- Prefer concrete types (dataclasses, TypedDicts, enums) over `dict[str, Any]`.

## Testing

- Mock all network calls (FiDI/Firefly) with `unittest.mock`.
- New features require new tests covering the added behavior.
- Mask account numbers in assertions — last four digits only (matches CLI behavior).

## Commits & PRs

- Imperative mood, scoped commits. Reference issue IDs when relevant.
- Update `CHANGELOG.md` under `Unreleased` for any user-facing or workflow changes.
- Release tags are strictly `vX.Y.Z`; replace `Unreleased` header with version + date when tagging.

## Configuration & Security

- Secrets live in `~/.local/etc/firefly_import.toml`; never commit them.
- Configure `ca_cert_path` for self-hosted Firefly instances with custom TLS certs.
- Log/display account numbers as last-four only.

## Releases

Run integration tests before tagging:

```bash
tox -e integration
```

Tests are skipped automatically if `~/.local/etc/firefly_import.toml` is absent. Both tests must pass before tagging.

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

CI builds sdist/wheel, creates the GitHub release, and updates the Homebrew formula automatically.
