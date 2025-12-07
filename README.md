# Firefly Preimporter

This repository contains the Firefly preimporter toolkit. The project is managed with [uv](https://github.com/astral-sh/uv) for dependency management, [Ruff](https://docs.astral.sh/ruff/) for linting/formatting, and [tox](https://tox.wiki/) for automation.

## Purpose

Firefly Preimporter is a transaction statement preprocessor: it ingests downloads from financial institutions (such as CSV or OFX statements), normalizes the data, and produces files compatible with the Firefly III Data Importer (FiDI). Every dataset we emit for FiDI includes these columns: account ID, transaction ID, date, description, and amount.

Output is provided in two forms:

1. A `.csv`/`.json` pair that FiDI can ingest manually.
2. An automated upload path that performs POST requests to FiDI directly.

## Requirements

- [uv](https://github.com/astral-sh/uv) (installs dependencies and creates the `.venv` used throughout)

After installing uv, run `uv sync` to set up the virtual environment and project dependencies.

## Tox commands

```bash
tox -e py311   # run the pytest suite
tox -e lint    # Ruff lint + format checks
```
