"""Phase 0.4 AC: ``python -c "import lineforge; print(lineforge.__version__)"`` works."""

from __future__ import annotations

import re

import lineforge


def test_version_attribute_present() -> None:
    assert hasattr(lineforge, "__version__")


def test_version_is_pep440() -> None:
    assert re.match(r"^\d+\.\d+\.\d+(?:[-.](?:a|b|rc|dev|post)\d+)?$", lineforge.__version__)


def test_version_module_matches_package() -> None:
    from lineforge.version import __version__ as v_module

    assert v_module == lineforge.__version__
