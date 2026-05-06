"""Phase 1.9 AC: atlc2 default material database is loaded and queryable."""

from __future__ import annotations

import pytest

from atlc3.materials.database import (
    ATLC2_DEFAULTS,
    find_by_name,
    list_atlc2_default,
    lookup_by_rgb,
)


def test_count_matches_atlc2_table() -> None:
    """atlc2 docs list 45 standard colors; we should have at least that many."""
    assert len(ATLC2_DEFAULTS) >= 45


def test_lookup_red_copper_plus_one() -> None:
    m = lookup_by_rgb((255, 0, 0))
    assert m is not None
    assert m.use == "+1"
    assert m.name == "copper"
    assert m.resistivity_ohm_cm == pytest.approx(1.7241)


def test_lookup_fr4() -> None:
    m = lookup_by_rgb((223, 247, 136))
    assert m is not None
    assert m.use == "insul"
    assert m.er == pytest.approx(3.7)


def test_find_by_name_substring_match() -> None:
    results = find_by_name("copper")
    assert len(results) >= 4  # +1, -1, 0, float copper variants

    fr4 = find_by_name("fr4")
    assert len(fr4) == 1


def test_unknown_rgb_returns_none() -> None:
    assert lookup_by_rgb((1, 2, 3)) is None


def test_records_are_immutable() -> None:
    m = ATLC2_DEFAULTS[0]
    # Pydantic v2 with frozen=True raises ValidationError on assignment
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        m.er = 99  # type: ignore[misc]


def test_list_returns_copy() -> None:
    a = list_atlc2_default()
    a.clear()
    assert len(ATLC2_DEFAULTS) >= 45  # original is untouched
