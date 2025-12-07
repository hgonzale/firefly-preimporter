# Firefly Preimporter

This repository contains the Firefly preimporter toolkit. The project is managed with [uv](https://github.com/astral-sh/uv) for dependency management, [Ruff](https://docs.astral.sh/ruff/) for linting/formatting, and [tox](https://tox.wiki/) for automation.

## Getting started

1. **Install uv** (if it is not already available): `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. **Create the virtual environment and install dependencies:**

   ```bash
   uv sync
   ```

   This installs the package in editable mode along with the dev dependencies defined in `pyproject.toml`.

3. **Activate the environment (optional):**

   ```bash
   source .venv/bin/activate
   ```

## Common tasks

- **Run the test suite:**

  ```bash
  uv run pytest
  # or
  tox -e py311
  ```

- **Lint & format:**

  ```bash
  uv run ruff check src tests
  uv run ruff format src tests
  # or run both via tox
  tox -e lint
  ```

- **Update dependencies:**

  ```bash
  uv add <package>
  uv remove <package>
  ```

## Repository layout

```
.
├── LICENSE
├── README.md
├── pyproject.toml
├── src/
│   └── firefly_preimporter/
│       └── __init__.py
└── tests/
    └── test_package.py
```

## Next steps

- Flesh out the package contents under `src/firefly_preimporter/`.
- Expand the test suite alongside new functionality.
- Consider CI automation (e.g., GitHub Actions) once the initial implementation is in place.
