"""Firefly preimporter package."""

from importlib import metadata as _metadata

def __getattr__(name: str) -> str:
    if name == "__version__":
        return _metadata.version("firefly-preimporter")
    raise AttributeError(name)

__all__ = ["__version__"]
