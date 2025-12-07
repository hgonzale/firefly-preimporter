"""Firefly preimporter package."""

from __future__ import annotations

from importlib import metadata as _metadata


def __getattr__(name: str) -> str:
    """Provide dynamic attributes such as ``__version__`` from package metadata."""

    if name == '__version__':
        return _metadata.version('firefly-preimporter')
    raise AttributeError(name)
