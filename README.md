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
- `-u/--upload` enables uploads (Firefly by default). Combine it with `--fidi` when you want to route the batch through FiDI auto-upload instead. While uploading, the CLI reuses OFX/QFX account numbers when possible; otherwise it fetches the asset list and prompts (you can bypass the prompt with `--account-id`, press `p` to preview, or `s` to skip the file).
- `--fidi` is only meaningful together with `-u/--upload`; it switches the uploader from Firefly to FiDI without altering other behavior.
- `-o/--output` accepts either a file path (single job) or a directory (multi-job/per-file; append a trailing `/` or point to an existing folder). During regular runs it writes the normalized CSV(s); when `-u firefly` is active it instead saves the generated Firefly API payload JSON.
- `-V/--version` prints the installed version and exits.
- `-n/--dry-run` only works together with `-u/--upload`; it runs the full normalization flow but skips the final FiDI/Firefly POST while still emitting previews/outputs for inspection.
- `--upload-duplicates` disables the duplicate-protection guards (FiDI’s `ignore_duplicate_*` flags and Firefly’s `error_if_duplicate_hash`) so reruns can intentionally inject historical data.

## Configuration

Copy `config.example.toml` (in the repo root) to `~/.local/etc/firefly_import.toml` and fill in your values.
Restrict permissions so only you can read it:

```bash
chmod 600 ~/.local/etc/firefly_import.toml
```

The example file documents every available option with comments, including the optional `[azure_ai]` block for AI-assisted account matching (see below).

### AI-assisted account matching (optional)

When `[azure_ai]` is configured and `openai` is installed (`pip install firefly-preimporter[ai]`), the upload prompt automatically suggests the most likely Firefly account for each CSV file.
The suggestion is based on two signals: whether the filename contains the last digits of an account number or a recognisable name, and whether the merchants and amounts in the file match the account's recent transaction history.

A single high-confidence suggestion is highlighted and offered as the default (press Enter to accept); multiple candidates are highlighted but require an explicit selection.
The feature is silently skipped when `[azure_ai]` is absent or `openai` is not installed.

## Installation

```bash
brew tap honkeandpastrami/tap
brew install honkeandpastrami/tap/firefly-preimporter
```

## Requirements

- [Homebrew](https://brew.sh)

## Tox commands

```bash
tox -e tests          # run the pytest suite with coverage (fails under 85%)
tox -e lint           # Ruff lint + format checks
tox -e types          # ty type checking
tox -e format         # auto-fix style issues with Ruff
tox -e brew-resources # refresh PyPI resource blocks in the Homebrew formula template
```
