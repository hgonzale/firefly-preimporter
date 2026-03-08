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


def _read_pyproject() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def get_python_cpver() -> str:
    """Return e.g. 'cp313' from requires-python = '>=3.13' in pyproject.toml."""
    req = _read_pyproject().get("project", {}).get("requires-python", "")
    m = re.search(r"(\d+)\.(\d+)", req)
    return f"cp{m.group(1)}{m.group(2)}" if m else ""


def _pick_wheel(candidates: list[tuple[str, str, str]], cpver: str) -> tuple[str | None, str | None]:
    """From a list of (url, sha, filename) tuples, prefer cpver match, else first."""
    if not candidates:
        return None, None
    if cpver:
        for url, sha, fname in candidates:
            if cpver in fname:
                return url, sha
    return candidates[0][0], candidates[0][1]


def parse_lock(cpver: str = "") -> dict[str, dict]:
    """Return {name: {version, sdist_url, sdist_sha, any_url, any_sha, arm64_url,
    arm64_sha, x86_url, x86_sha, deps}} for all packages in uv.lock."""
    text = LOCK.read_text()
    packages: dict[str, dict] = {}
    for block in text.split("\n[[package]]\n"):
        name_m = re.search(r'^name = "([^"]+)"', block, re.MULTILINE)
        ver_m = re.search(r'^version = "([^"]+)"', block, re.MULTILINE)
        sdist_m = re.search(r'sdist = \{ url = "([^"]+)", hash = "sha256:([^"]+)"', block)
        deps = re.findall(r'  \{ name = "([^"]+)" \}', block)

        any_url = any_sha = None
        arm64_candidates: list[tuple[str, str, str]] = []
        x86_candidates: list[tuple[str, str, str]] = []

        wheels_m = re.search(r"wheels = \[(.*?)\]", block, re.DOTALL)
        if wheels_m:
            for entry in re.finditer(r'\{ url = "([^"]+)", hash = "sha256:([^"]+)"', wheels_m.group(1)):
                url, sha = entry.group(1), entry.group(2)
                fname = url.rsplit("/", 1)[-1]
                if "none-any" in fname:
                    any_url, any_sha = url, sha
                elif re.search(r"macosx_\d+_\d+_arm64", fname):
                    arm64_candidates.append((url, sha, fname))
                elif re.search(r"macosx_\d+_\d+_x86_64", fname):
                    x86_candidates.append((url, sha, fname))

        arm64_url, arm64_sha = _pick_wheel(arm64_candidates, cpver)
        x86_url, x86_sha = _pick_wheel(x86_candidates, cpver)

        if name_m:
            packages[name_m.group(1)] = {
                "version": ver_m.group(1) if ver_m else None,
                "sdist_url": sdist_m.group(1) if sdist_m else None,
                "sdist_sha": sdist_m.group(2) if sdist_m else None,
                "any_url": any_url,
                "any_sha": any_sha,
                "arm64_url": arm64_url,
                "arm64_sha": arm64_sha,
                "x86_url": x86_url,
                "x86_sha": x86_sha,
                "deps": deps,
            }
    return packages


def get_direct_runtime_deps() -> set[str]:
    """Read [project].dependencies from pyproject.toml and return bare package names."""
    deps = _read_pyproject().get("project", {}).get("dependencies", [])
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


def make_resource_block(name: str, info: dict) -> str | None:
    """Return the Homebrew resource block string for a package, or None to skip."""
    # Priority 1: universal wheel (py3-none-any) — works on all platforms, no build
    if info["any_url"]:
        return (
            f'  resource "{name}" do\n'
            f'    url "{info["any_url"]}"\n'
            f'    sha256 "{info["any_sha"]}"\n'
            f"  end"
        )
    # Priority 2: macOS platform-specific wheels — compiled extension, no Rust needed
    if info["arm64_url"] and info["x86_url"]:
        return (
            f"  on_arm do\n"
            f'    resource "{name}" do\n'
            f'      url "{info["arm64_url"]}"\n'
            f'      sha256 "{info["arm64_sha"]}"\n'
            f"    end\n"
            f"  end\n"
            f"  on_intel do\n"
            f'    resource "{name}" do\n'
            f'      url "{info["x86_url"]}"\n'
            f'      sha256 "{info["x86_sha"]}"\n'
            f"    end\n"
            f"  end"
        )
    # Priority 3: sdist fallback (pure Python packages with no wheels, e.g. ofxtools)
    if info["sdist_url"]:
        return (
            f'  resource "{name}" do\n'
            f'    url "{info["sdist_url"]}"\n'
            f'    sha256 "{info["sdist_sha"]}"\n'
            f"  end"
        )
    return None


def main() -> None:
    cpver = get_python_cpver()
    packages = parse_lock(cpver)
    direct = get_direct_runtime_deps()
    runtime = get_runtime_packages(packages, direct)

    blocks: list[str] = []
    for pkg in sorted(runtime):
        info = packages.get(pkg)
        if not info:
            print(f"WARNING: {pkg} not found in uv.lock, skipping", file=sys.stderr)
            continue
        block = make_resource_block(pkg, info)
        if block is None:
            print(f"WARNING: {pkg} has no wheel or sdist in uv.lock, skipping", file=sys.stderr)
            continue
        blocks.append(block)
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
