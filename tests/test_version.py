"""Phase 0.4 AC: ``python -c "import atlc3; print(atlc3.__version__)"`` works."""

from __future__ import annotations

import re

import atlc3


def test_version_attribute_present() -> None:
    assert hasattr(atlc3, "__version__")


def test_version_is_pep440() -> None:
    assert re.match(r"^\d+\.\d+\.\d+(?:[-.](?:a|b|rc|dev|post)\d+)?$", atlc3.__version__)


def test_version_module_matches_package() -> None:
    from atlc3.version import __version__ as v_module

    assert v_module == atlc3.__version__
