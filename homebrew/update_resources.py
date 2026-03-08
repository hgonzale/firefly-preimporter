"""
Regenerate the `resource` blocks in homebrew/firefly-preimporter.rb.template
from the locked runtime deps in uv.lock.

Usage: python homebrew/update_resources.py
       (or via: tox -e brew-resources)
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).parent.parent
TEMPLATE = REPO / "homebrew" / "firefly-preimporter.rb.template"
LOCK = REPO / "uv.lock"
PYPROJECT = REPO / "pyproject.toml"


def parse_lock() -> dict[str, dict]:
    """Return {name: {version, sdist_url, sdist_sha, deps}} for all packages in uv.lock."""
    text = LOCK.read_text()
    packages: dict[str, dict] = {}
    for block in text.split("\n[[package]]\n"):
        name_m = re.search(r'^name = "([^"]+)"', block, re.MULTILINE)
        ver_m = re.search(r'^version = "([^"]+)"', block, re.MULTILINE)
        sdist_m = re.search(r'sdist = \{ url = "([^"]+)", hash = "sha256:([^"]+)"', block)
        deps = re.findall(r'  \{ name = "([^"]+)" \}', block)
        if name_m:
            packages[name_m.group(1)] = {
                "version": ver_m.group(1) if ver_m else None,
                "sdist_url": sdist_m.group(1) if sdist_m else None,
                "sdist_sha": sdist_m.group(2) if sdist_m else None,
                "deps": deps,
            }
    return packages


def get_direct_runtime_deps() -> set[str]:
    """Read [project].dependencies from pyproject.toml and return bare package names."""
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    return {re.split(r"[<>=!;\s]", dep)[0].strip() for dep in deps}


def get_runtime_packages(packages: dict[str, dict], direct: set[str]) -> set[str]:
    """BFS from direct runtime deps to collect all transitive runtime packages."""
    seen: set[str] = set()
    queue = list(direct)
    while queue:
        pkg = queue.pop()
        if pkg in seen:
            continue
        seen.add(pkg)
        queue.extend(packages.get(pkg, {}).get("deps", []))
    return seen


def main() -> None:
    packages = parse_lock()
    direct = get_direct_runtime_deps()
    runtime = get_runtime_packages(packages, direct)

    blocks: list[str] = []
    for pkg in sorted(runtime):
        info = packages.get(pkg)
        if not info:
            print(f"WARNING: {pkg} not found in uv.lock, skipping", file=sys.stderr)
            continue
        if not info["sdist_url"]:
            print(f"WARNING: {pkg} has no sdist in uv.lock, skipping", file=sys.stderr)
            continue
        blocks.append(
            f'  resource "{pkg}" do\n'
            f'    url "{info["sdist_url"]}"\n'
            f'    sha256 "{info["sdist_sha"]}"\n'
            f"  end"
        )
        print(f"  {pkg}=={info['version']}")

    resource_block = "\n\n".join(blocks)
    template = TEMPLATE.read_text()
    new_template = re.sub(
        r"(  # --- begin generated resources ---\n).*?(  # --- end generated resources ---)",
        rf"\g<1>{resource_block}\n\2",
        template,
        flags=re.DOTALL,
    )
    TEMPLATE.write_text(new_template)
    print(f"\nWrote {len(blocks)} resource blocks to {TEMPLATE.relative_to(REPO)}")


if __name__ == "__main__":
    main()
