"""Wheeler incremental-inductance resistance: sqrt(f) scaling, symmetry, and the wide-strip closed form."""

from __future__ import annotations

import math

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord, RoughnessSpec
from lineforge.solvers import extension
from lineforge.solvers.mtl import solve_maxwell
from lineforge.solvers.wheeler import solve_wheeler_resistance

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
MU0 = 4e-7 * math.pi
RHO = 1.7241e-8


@pytest.fixture(autouse=True)
def _fast_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    def _small(usermap: Usermap, **_kw: object) -> Usermap:
        return usermap.replicate_edges(6)

    monkeypatch.setattr(extension, "extend", _small)


def parallel_plate(width_px: int = 80, gap_px: int = 8, t_px: int = 5, px: float = 1e-5) -> Usermap:
    h = gap_px + 2 * t_px + 20
    w = width_px + 40
    mat = np.full((h, w), -1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    top = slice(10, 10 + t_px)
    bot = slice(10 + t_px + gap_px, 10 + 2 * t_px + gap_px)
    cols = slice(20, 20 + width_px)
    mat[top, cols] = 0
    cid[top, cols] = 1
    mat[bot, cols] = 0
    cid[bot, cols] = 0
    return Usermap.from_labels(mat, [CU], pixel_width_m=px, conductor_ids=cid)


def test_sqrt_f_scaling_and_internal_inductance() -> None:
    u = parallel_plate()
    base = solve_maxwell(u, method="sor", tol=1e-6, extend_grid=True)
    r1 = solve_wheeler_resistance(u, frequency_hz=1e9, base=base, method="sor", tol=1e-6)
    r4 = solve_wheeler_resistance(u, frequency_hz=4e9, base=base, method="sor", tol=1e-6)
    assert r4.R_per_m[0, 0] == pytest.approx(2.0 * r1.R_per_m[0, 0], rel=1e-9)
    assert r1.L_int_per_m[0, 0] == pytest.approx(r1.R_per_m[0, 0] / (2 * math.pi * 1e9))
    assert not [w for w in r1.warnings if w.severity == "error"]


def test_symmetric_pair_contributes_equally() -> None:
    """The two plates of a symmetric parallel-plate line lose the same amount."""
    u = parallel_plate()
    res = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)
    assert set(res.per_conductor) == {0, 1}
    # Equal to the solver tolerance: the two eroded solves are mirror images of each other.
    assert res.per_conductor[1][0, 0] == pytest.approx(res.per_conductor[0][0, 0], rel=1e-6)
    assert res.per_conductor[1][0, 0] > 0.0


def test_wide_parallel_plate_matches_closed_form() -> None:
    """Wide parallel plates: R = 2 Rs / W per metre (both conductors), within the pixel discretisation."""
    px = 1e-5
    width_px = 80
    u = parallel_plate(width_px=width_px, gap_px=8, t_px=5, px=px)
    f = 5e9
    res = solve_wheeler_resistance(u, frequency_hz=f, method="sor", tol=1e-6)
    rs = math.sqrt(math.pi * f * MU0 * RHO)
    expected = 2.0 * rs / (width_px * px)
    assert res.R_per_m[0, 0] == pytest.approx(expected, rel=0.25)


def test_roughness_scales_only_the_rough_conductor() -> None:
    u = parallel_plate()
    smooth = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)
    rough = solve_wheeler_resistance(
        u,
        frequency_hz=5e9,
        method="sor",
        tol=1e-6,
        roughness={1: RoughnessSpec(model="hammerstad", rms_um=2.0)},
    )
    k = rough.roughness_factors[1]
    assert k > 1.5
    assert rough.roughness_factors[0] == 1.0
    contribution_signal = smooth.per_conductor[1][0, 0]
    contribution_ref = smooth.per_conductor[0][0, 0]
    assert rough.R_per_m[0, 0] == pytest.approx(
        k * contribution_signal + contribution_ref, rel=1e-9
    )


def test_conductor_too_thin_is_skipped_with_a_warning() -> None:
    u = parallel_plate(t_px=1)
    res = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)
    codes = {w.code for w in res.warnings}
    assert "conductor_too_thin_for_wheeler" in codes
    assert res.per_conductor == {}
    assert res.R_per_m.shape == (1, 1)


def test_skin_depth_not_small_is_reported() -> None:
    u = parallel_plate()
    res = solve_wheeler_resistance(u, frequency_hz=1e6, method="sor", tol=1e-6)
    assert "skin_depth_not_small" in {w.code for w in res.warnings}
