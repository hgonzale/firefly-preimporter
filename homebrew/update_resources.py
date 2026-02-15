"""
Regenerate the `resource` blocks in homebrew/firefly-preimporter.rb.template
from the locked runtime deps in uv.lock.

Usage: python homebrew/update_resources.py
       (or via: tox -e brew-resources)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests  # noqa: PLC0415

REPO = Path(__file__).parent.parent
TEMPLATE = REPO / "homebrew" / "firefly-preimporter.rb.template"
LOCK = REPO / "uv.lock"

# Runtime dep names (direct + transitive, no dev deps)
RUNTIME_PACKAGES = {"requests", "ofxtools", "urllib3", "certifi", "charset-normalizer", "idna"}


def get_sdist_info(name: str, version: str) -> tuple[str, str]:
    """Return (url, sha256) for the sdist of name==version from PyPI."""
    resp = requests.get(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    for f in data["urls"]:
        if f["packagetype"] == "sdist":
            return f["url"], f["digests"]["sha256"]
    raise SystemExit(f"No sdist found for {name}=={version}")


def parse_lock() -> dict[str, str]:
    """Return {name: version} for all packages in uv.lock."""
    text = LOCK.read_text()
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'^name = "([^"]+)"\nversion = "([^"]+)"', text, re.MULTILINE)
    }


def main() -> None:
    locked = parse_lock()
    blocks: list[str] = []
    for pkg in sorted(RUNTIME_PACKAGES):
        version = locked.get(pkg)
        if not version:
            print(f"WARNING: {pkg} not found in uv.lock, skipping", file=sys.stderr)
            continue
        url, sha256 = get_sdist_info(pkg, version)
        blocks.append(
            f'  resource "{pkg}" do\n'
            f'    url "{url}"\n'
            f'    sha256 "{sha256}"\n'
            f"  end"
        )
        print(f"  {pkg}=={version}")

    resource_block = "\n\n".join(blocks)
    template = TEMPLATE.read_text()
    # Replace everything between the two marker comments
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
