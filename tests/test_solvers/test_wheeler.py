"""Wheeler incremental-inductance resistance: sqrt(f) scaling, symmetry, and the wide-strip closed form."""

from __future__ import annotations

import math

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord, RoughnessSpec
from lineforge.solvers import extension
from lineforge.solvers.mtl import solve_maxwell
from lineforge.solvers.wheeler import _eroded_copy, solve_wheeler_resistance

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
MU0 = 4e-7 * math.pi
RHO = 1.7241e-8


@pytest.fixture(autouse=True)
def _fast_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    def _small(usermap: Usermap, **_kw: object) -> Usermap:
        return usermap.replicate_edges(6)

    monkeypatch.setattr(extension, "extend", _small)


def parallel_plate(
    width_px: int = 80,
    gap_px: int = 8,
    t_px: int = 5,
    px: float = 1e-5,
    t_signal_px: int | None = None,
) -> Usermap:
    """Two plates: the signal (id 1) on top, the reference (id 0) below, vacuum between."""
    t_sig = t_px if t_signal_px is None else t_signal_px
    h = gap_px + t_px + t_sig + 20
    w = width_px + 40
    mat = np.full((h, w), -1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    top = slice(10, 10 + t_sig)
    bot = slice(10 + t_sig + gap_px, 10 + t_sig + gap_px + t_px)
    cols = slice(20, 20 + width_px)
    mat[top, cols] = 0
    cid[top, cols] = 1
    mat[bot, cols] = 0
    cid[bot, cols] = 0
    return Usermap.from_labels(mat, [CU], pixel_width_m=px, conductor_ids=cid)


def microstrip_over_edge_plane(
    width_px: int = 20, t_px: int = 5, h_px: int = 8, px: float = 1e-5
) -> Usermap:
    """A reference plane spanning every column and running off the bottom edge of the map."""
    w = width_px + 60
    height = 12 + t_px + h_px + t_px
    mat = np.full((height, w), -1, dtype=np.int32)
    cid = np.full((height, w), -1, dtype=np.int32)
    mat[height - t_px :, :] = 0
    cid[height - t_px :, :] = 0
    strip = slice(height - 2 * t_px - h_px, height - t_px - h_px)
    cols = slice((w - width_px) // 2, (w - width_px) // 2 + width_px)
    mat[strip, cols] = 0
    cid[strip, cols] = 1
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
    """A one-pixel signal cannot be eroded; the reference still carries its own loss."""
    u = parallel_plate(t_signal_px=1)
    res = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)
    assert "conductor_too_thin_for_wheeler" in {w.code for w in res.warnings}
    assert set(res.per_conductor) == {0}
    assert res.R_per_m[0, 0] > 0.0


def test_no_conductor_erodes_is_an_error() -> None:
    u = parallel_plate(t_px=1, t_signal_px=1)
    with pytest.raises(ValueError, match="no conductor could be eroded"):
        solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)


def test_skin_depth_not_small_is_reported() -> None:
    u = parallel_plate()
    res = solve_wheeler_resistance(u, frequency_hz=1e6, method="sor", tol=1e-6)
    assert "skin_depth_not_small" in {w.code for w in res.warnings}


def test_edge_touching_plane_keeps_its_full_width_under_erosion() -> None:
    """A plane that runs off the map edge is cut only on its inner face, not at the border."""
    u = microstrip_over_edge_plane()
    eroded = _eroded_copy(u, 0, 1)
    assert eroded is not None
    plane = u.conductor_ids == 0
    eroded_plane = eroded.conductor_ids == 0
    assert eroded_plane.any(axis=0).all()  # every column still has plane
    assert eroded_plane.any(axis=1).sum() == plane.any(axis=1).sum() - 1  # exactly one row gone
    assert eroded_plane.sum() == plane.sum() - u.shape[1]

    res = solve_wheeler_resistance(u, frequency_hz=1e10, method="sor", tol=1e-6)
    assert res.per_conductor[0][0, 0] > 0.0
    assert res.per_conductor[1][0, 0] > 0.0
    # The plane is semi-infinite once the border is replicated, so the skin always fits.
    assert "skin_depth_not_small" not in {w.code for w in res.warnings}


def test_reused_geometry_derivative_matches_a_fresh_solve() -> None:
    u = parallel_plate()
    r1 = solve_wheeler_resistance(u, frequency_hz=1e9, method="sor", tol=1e-6)
    fresh = solve_wheeler_resistance(u, frequency_hz=7e9, method="sor", tol=1e-6)
    reused = solve_wheeler_resistance(u, frequency_hz=7e9, dl_dn=r1.dL_dn)
    assert reused.R_per_m[0, 0] == pytest.approx(fresh.R_per_m[0, 0], rel=1e-12)
    assert reused.dL_dn.keys() == fresh.dL_dn.keys()


def test_base_solver_warnings_reach_the_result() -> None:
    """A conductor pixel with no conductor id is pinned to the reference; say so here too."""
    u = parallel_plate()
    u.codes[2, 2] = 0  # a stray copper pixel that no conductor_ids entry claims
    res = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)
    codes = [w.code for w in res.warnings]
    assert "unlabelled_conductor_pixels" in codes
    assert codes.count("unlabelled_conductor_pixels") == 1  # not repeated per eroded solve


def test_conductor_without_material_is_an_error_warning() -> None:
    u = parallel_plate()
    u.conductor_ids[2, 2] = -2  # a floating label on a vacuum pixel
    res = solve_wheeler_resistance(u, frequency_hz=5e9, method="sor", tol=1e-6)
    bad = [w for w in res.warnings if w.code == "conductor_without_material"]
    assert len(bad) == 1
    assert bad[0].severity == "error"
    assert set(res.per_conductor) == {0, 1}


def test_roughness_for_an_absent_id_is_reported() -> None:
    u = parallel_plate()
    res = solve_wheeler_resistance(
        u,
        frequency_hz=5e9,
        method="sor",
        tol=1e-6,
        roughness={7: RoughnessSpec(model="hammerstad", rms_um=2.0)},
    )
    assert "roughness_id_not_in_map" in {w.code for w in res.warnings}
    assert 7 not in res.roughness_factors
