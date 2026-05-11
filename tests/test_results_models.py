"""Phase 0.4 AC: Pydantic v2 models with proper field validators round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lineforge.geometry.types import Microstrip
from lineforge.results import DiffResult, SolverWarning, TLineResult


def test_microstrip_round_trip() -> None:
    m = Microstrip(W=152e-6, H=102e-6, T=35e-6, er=4.4)
    blob = m.model_dump_json()
    restored = Microstrip.model_validate_json(blob)
    assert restored == m


def test_microstrip_validates_positive_dimensions() -> None:
    with pytest.raises(ValidationError):
        Microstrip(W=-1e-6, H=102e-6, T=35e-6, er=4.4)


def test_microstrip_validates_er_at_least_one() -> None:
    with pytest.raises(ValidationError):
        Microstrip(W=152e-6, H=102e-6, T=35e-6, er=0.5)


def test_microstrip_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Microstrip(W=152e-6, H=102e-6, T=35e-6, er=4.4, bogus=1)  # type: ignore[call-arg]


def test_tline_result_minimal() -> None:
    r = TLineResult(
        z0=50.0,
        eps_eff=2.9,
        vp=1.76e8,
        td_per_inch=1.44e-10,
        method="hammerstad",
    )
    assert r.warnings == []


def test_tline_result_warnings_attach() -> None:
    w = SolverWarning(code="out_of_range", message="W/H exceeds 20", severity="warning")
    r = TLineResult(
        z0=10.0,
        eps_eff=2.9,
        vp=1.76e8,
        td_per_inch=1.44e-10,
        method="hammerstad",
        warnings=[w],
    )
    assert r.warnings[0].code == "out_of_range"


def test_diff_result() -> None:
    r = DiffResult(
        z_odd=50.0,
        z_even=60.0,
        z_diff=100.0,
        z_common=30.0,
        eps_eff_odd=2.9,
        eps_eff_even=3.0,
        vp_odd=1.76e8,
        vp_even=1.73e8,
        method="wadell",
    )
    assert pytest.approx(r.z_diff) == 2 * r.z_odd
    assert pytest.approx(r.z_common) == r.z_even / 2
