# firefly-preimporter

## Before cutting a release

Run integration tests against the real config and live APIs before tagging a new version:

```bash
pytest tests/integration/ -v
```

Tests are skipped automatically if `~/.local/etc/firefly_import.toml` is absent.
Both tests must pass before tagging.

## Tagging a release

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

CI builds the sdist/wheel, creates the GitHub release, and pushes the updated
formula to the Homebrew tap automatically.
