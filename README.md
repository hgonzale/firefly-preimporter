# Firefly Preimporter

This repository contains the Firefly preimporter toolkit. The project is managed with [uv](https://github.com/astral-sh/uv) for dependency management, [Ruff](https://docs.astral.sh/ruff/) for linting/formatting, and [tox](https://tox.wiki/) for automation.

## Purpose

Firefly Preimporter is a transaction statement preprocessor: it ingests downloads from financial institutions (such as CSV or OFX statements), normalizes the data, and produces files compatible with the Firefly III Data Importer (FiDI). Every dataset we emit for FiDI includes these columns: account ID, transaction ID, date, description, and amount.

Output is provided in two forms:

1. A `.csv`/`.json` pair that FiDI can ingest manually.
2. An automated upload path that performs POST requests to FiDI directly.

## CLI usage

The CLI entry point is `firefly-preimporter`. Example:

```bash
uv run firefly-preimporter statements/ --output-dir normalized
```

Key flags:

- `--stdout` only works for a single input target.
- When no output flags are provided, each file produces `<name>.firefly.csv` next to the original input.
- `-s/--auto-upload` (optionally paired with `-n/--dry-run`) reads FiDI credentials from the TOML config, attempts to reuse the account id embedded in OFX/QFX files, and otherwise fetches the list of asset accounts from Firefly for per-file interactive selection (or you can bypass the prompt with `--account-id`).
- `-o/--output` targets a single file, while `--output-dir` writes per-job files; `-q/--quiet` and `-v/--verbose` adjust log chatter for multi-file runs.

## Requirements

- [uv](https://github.com/astral-sh/uv) (installs dependencies and creates the `.venv` used throughout)

After installing uv, run `uv sync` to set up the virtual environment and project dependencies.

## Tox commands

```bash
tox -e py311   # run the pytest suite with coverage (fails under 85%)
tox -e lint    # Ruff lint + format checks
tox -e types   # Pyright type checking
tox -e format  # auto-fix style issues with Ruff
```
