# Homebrew

## Files

| File | Purpose |
|------|---------|
| `firefly-preimporter.rb.template` | Formula template; CI fills in `url`/`sha256`/`version` on each tag push and commits the result to [honkeandpastrami/homebrew-tap](https://github.com/honkeandpastrami/homebrew-tap) |
| `update_resources.py` | Regenerates PyPI resource blocks from `uv.lock` — run via `tox -e brew-resources` after any runtime dep changes, then commit the updated template |
