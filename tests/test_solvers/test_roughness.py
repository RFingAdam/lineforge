"""Roughness correction factors: limits and one hand-computed cannonball value."""

from __future__ import annotations

import math

import pytest

from lineforge.materials.database import MaterialRecord, RoughnessSpec
from lineforge.solvers.roughness import (
    cannonball_from_rz,
    groisse_factor,
    hammerstad_factor,
    huray_factor,
    roughness_factor,
)
from lineforge.solvers.skin_depth import compute_delta

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")


def test_hammerstad_limits() -> None:
    assert hammerstad_factor(1e-3, 1e-6) == pytest.approx(1.0, abs=1e-4)
    assert hammerstad_factor(1e-9, 1e-6) == pytest.approx(2.0, abs=1e-4)
    assert hammerstad_factor(1e-6, 1e-6) == pytest.approx(1 + (2 / math.pi) * math.atan(1.4))


def test_groisse_limits() -> None:
    assert groisse_factor(1e-3, 1e-6) == pytest.approx(1.0, abs=1e-6)
    assert groisse_factor(1e-9, 1e-6) == pytest.approx(2.0, abs=1e-3)


def test_huray_cannonball_hand_value() -> None:
    a, ratio = cannonball_from_rz(6e-6)
    assert a == pytest.approx(6e-6 / (2 * (1 + math.sqrt(2))))
    assert ratio == pytest.approx(14 * 4 * math.pi / 36)
    delta = compute_delta(CU, 10e9)
    k = huray_factor(delta, a, ratio)
    expected = 1 + 1.5 * ratio / (1 + delta / a + delta**2 / (2 * a * a))
    assert k == pytest.approx(expected)
    assert huray_factor(1e-3, a, ratio) == pytest.approx(1.0, abs=1e-3)
    assert huray_factor(1e-12, a, ratio) == pytest.approx(1 + 1.5 * ratio, rel=1e-4)


def test_dispatch_by_spec() -> None:
    delta = compute_delta(CU, 5e9)
    assert roughness_factor(RoughnessSpec(model="hammerstad", rms_um=1.0), delta) == pytest.approx(
        hammerstad_factor(delta, 1e-6)
    )
    assert roughness_factor(RoughnessSpec(model="groisse", rms_um=1.0), delta) == pytest.approx(
        groisse_factor(delta, 1e-6)
    )
    spec = RoughnessSpec(model="huray", rz_um=6.0)
    assert roughness_factor(spec, delta) == pytest.approx(
        huray_factor(delta, spec.radius_um * 1e-6, spec.ratio)  # type: ignore[arg-type]
    )
