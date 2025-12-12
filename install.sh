#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found in PATH." >&2
  exit 1
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_uv() {
  (
    cd "$repo_dir"
    unset VIRTUAL_ENV
    unset UV_PROJECT_ENVIRONMENT
    unset UV_PROJECT_FILE
    export UV_NO_PROJECT=1
    uv "$@"
  )
}

run_uv build --wheel --sdist >/dev/null

pkg_version="$(
  cd "$repo_dir"
  python - <<'PY'
import pathlib, sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required to parse pyproject.toml")
data = pathlib.Path("pyproject.toml").read_text(encoding="utf-8")
import tomllib
info = tomllib.loads(data)
print(info["project"]["version"])
PY
)"

wheel_path="${repo_dir}/dist/firefly_preimporter-${pkg_version}-py3-none-any.whl"
if [[ ! -f "${wheel_path}" ]]; then
  echo "Wheel not found at ${wheel_path}. Run 'uv build' manually and retry." >&2
  exit 1
fi

run_uv tool uninstall firefly-preimporter >/dev/null 2>&1 || true
run_uv tool install "${wheel_path}" --force

echo "firefly-preimporter installed to \${HOME}/.local/bin (via uv tool install)."
