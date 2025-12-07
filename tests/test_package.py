import importlib


def test_package_importable() -> None:
    module = importlib.import_module('firefly_preimporter')
    assert hasattr(module, '__version__')
