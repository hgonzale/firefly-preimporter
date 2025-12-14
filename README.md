# Firefly Preimporter

This repository contains the Firefly preimporter toolkit. The project is managed with [uv](https://github.com/astral-sh/uv) for dependency management, [Ruff](https://docs.astral.sh/ruff/) for linting/formatting, and [tox](https://tox.wiki/) for automation.

## Purpose

Firefly Preimporter is a transaction statement preprocessor: it ingests downloads from financial institutions (such as CSV or OFX statements), normalizes the data, and produces files compatible with the [Firefly III](https://github.com/firefly-iii/firefly-iii) Data Importer (FiDI). Every dataset we emit for FiDI includes these columns: account ID, transaction ID, date, description, and amount.

Output is provided in two forms:

1. A `.csv`/`.json` pair that FiDI can ingest manually.
2. An automated upload path that performs POST requests to FiDI directly.

## CLI usage

The CLI entry point is `firefly-preimporter`. Example:

```bash
uv run firefly-preimporter statements/ --output normalized/
```

Key flags:

- `--stdout` only works for a single input target (and when combined with `-n/--dry-run` it prints the JSON config preview to stderr alongside the CSV).
- When no output flags are provided (and `-u` is not used), each file produces `<name>.firefly.csv` next to the original input.
- `-u/--upload [firefly|fidi]` enables uploads. Use `-u` (or `-u firefly`) to post directly to the Firefly API (default), or pass `-u fidi` for FiDI auto-upload. While uploading, the CLI reuses OFX/QFX account numbers when possible; otherwise it fetches the asset list and prompts (you can bypass the prompt with `--account-id`, press `p` to preview, or `s` to skip the file).
- `-o/--output` accepts either a file path (single job) or a directory (multi-job/per-file; append a trailing `/` or point to an existing folder). During regular runs it writes the normalized CSV(s); when `-u firefly` is active it instead saves the generated Firefly API payload JSON.
- `-V/--version` prints the installed version and exits.
- `-n/--dry-run` only works together with `-u/--upload`; it runs the full normalization flow but skips the final FiDI/Firefly POST while still emitting previews/outputs for inspection.
- `--upload-duplicates` disables the duplicate-protection guards (FiDI’s `ignore_duplicate_*` flags and Firefly’s `error_if_duplicate_hash`) so reruns can intentionally inject historical data.

## Configuration

Place a TOML file (default `~/.local/etc/firefly_import.toml`) with your API credentials and knobs such as:

```toml
personal_access_token = "..."
fidi_import_secret = "..."
firefly_error_on_duplicate = true  # keep true to mirror FiDI duplicate-hash checks
default_upload = "firefly"        # optional: auto-run `-u firefly` (valid values: "fidi", "firefly", or empty)
```

All other FiDI settings (like the JSON roles/mapping) remain under `[default_json_config]`. When `firefly_error_on_duplicate` stays true (the default) every Firefly upload we generate carries `error_if_duplicate_hash=true`, matching FiDI's duplicate-protection behavior; flip it off only if you explicitly want Firefly III to accept potentially duplicated transactions.

## Installation

Use the bundled script to install or refresh the uv-managed CLI in `~/.local/bin` (it safely ignores any active virtual environment):

```bash
./install.sh
```

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
