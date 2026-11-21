"""Smoke test: the package installs and reports the version from pyproject.toml."""

import bogota_syntax


def test_version_is_set() -> None:
    assert bogota_syntax.__version__ == "0.0.0"
