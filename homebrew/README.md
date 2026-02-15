# Homebrew

## Install / upgrade

```bash
./brew-setup.sh
```

Fetches the formula from the latest GitHub release, registers the tap (first run only), then installs or upgrades.

## Files

| File | Purpose |
|------|---------|
| `firefly-preimporter.rb.template` | Committed template; CI fills in `url`/`sha256`/`version` at release time |
| `update_resources.py` | Regenerates PyPI resource blocks from `uv.lock` |
| `Formula/` | Gitignored; populated by `brew-setup.sh` at install time |

## Refresh PyPI resource blocks

Run after any runtime dep changes in `uv.lock`:

```bash
tox -e brew-resources
```

Then commit the updated template.

## How releases work

On tag push, CI:
1. Builds the sdist
2. Fills in the template placeholders
3. Uploads `firefly-preimporter.rb` as a release asset

`brew-setup.sh` downloads that asset into `Formula/` and installs from it.
