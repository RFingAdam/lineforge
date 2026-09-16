"""Maxwell capacitance matrices reduce to the existing single-line and differential solvers."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import DSParams, MaterialRecord
from lineforge.solvers import cgp, diff_modes, extension
from lineforge.solvers.mtl import rlgc_matrices, solve_maxwell

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
CU2 = MaterialRecord(rgb=(0, 0, 255), use="-1", name="copper2")
GND = MaterialRecord(rgb=(0, 255, 0), use="0", name="ground")
FR4 = MaterialRecord(
    rgb=(223, 247, 136),
    use="insul",
    er=3.7,
    tan_delta=0.018,
    name="FR4",
    resistivity_ohm_cm=1e6,
)


@pytest.fixture(autouse=True)
def _fast_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    def _small(usermap: Usermap, **_kw: object) -> Usermap:
        return usermap.replicate_edges(4)

    monkeypatch.setattr(cgp.extension, "extend", _small)
    monkeypatch.setattr(diff_modes.extension, "extend", _small)
    monkeypatch.setattr(extension, "extend", _small)


def stripline_pair(with_second: bool) -> tuple[Usermap, Usermap]:
    """Two label maps of the same geometry: one with fieldforge ids, one RGB-role encoded."""
    h, w = 30, 60
    mat = np.full((h, w), 1, dtype=np.int32)  # FR4 everywhere
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[0, :] = 0
    cid[0, :] = 0
    mat[h - 1, :] = 0
    cid[h - 1, :] = 0
    mat[14:16, 15:25] = 0
    cid[14:16, 15:25] = 1
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[:] = FR4.rgb
    rgb[0, :] = GND.rgb
    rgb[h - 1, :] = GND.rgb
    rgb[14:16, 15:25] = CU.rgb
    if with_second:
        mat[14:16, 35:45] = 0
        cid[14:16, 35:45] = 2
        rgb[14:16, 35:45] = CU2.rgb
    labels = Usermap.from_labels(mat, [CU, FR4], pixel_width_m=2e-5, conductor_ids=cid)
    roles = Usermap(rgb, labels.meta, unknown_warning=False)
    return labels, roles


def test_single_conductor_matches_solve_cgp() -> None:
    labels, roles = stripline_pair(with_second=False)
    res = solve_maxwell(labels, method="sor", tol=1e-6, extend_grid=True)
    C, G, L = rlgc_matrices(res, 1e9)
    ref = cgp.solve_cgp(roles, frequency_hz=1e9, method="sor", tol=1e-6, extend_grid=True)
    assert C.shape == (1, 1)
    assert C[0, 0] == pytest.approx(ref.C_per_m, rel=2e-3)
    assert L[0, 0] == pytest.approx(ref.L_per_m, rel=2e-3)
    assert G[0, 0] == pytest.approx(ref.Gp_per_m, rel=2e-3)


def test_pair_reduces_to_odd_and_even_modes() -> None:
    labels, roles = stripline_pair(with_second=True)
    res = solve_maxwell(labels, method="sor", tol=1e-6, extend_grid=True)
    C, _, L = rlgc_matrices(res, 1e9)
    assert C.shape == (2, 2)
    assert C[0, 1] < 0 < C[0, 0]
    modes = diff_modes.solve_modes(roles)
    c_odd = C[0, 0] - C[0, 1]
    c_even = C[0, 0] + C[0, 1]
    z_odd = np.sqrt((L[0, 0] - L[0, 1]) / c_odd)
    z_even = np.sqrt((L[0, 0] + L[0, 1]) / c_even)
    assert z_odd == pytest.approx(modes.z_odd, rel=3e-3)
    assert z_even == pytest.approx(modes.z_even, rel=3e-3)
    # Every row of a Maxwell matrix sums to that conductor's capacitance to the reference,
    # which has to be positive. Unlike ``C[0, 1] == C[1, 0]`` (symmetric by construction in
    # ``_energy_matrices``) or ``eigvalsh(C) > 0`` on a 2x2 whose signs were just asserted,
    # this one fails if the reference is mislabelled or a sign is dropped.
    assert (C.sum(axis=1) > 0).all()


def test_keep_fields_and_warnings_shape() -> None:
    labels, _ = stripline_pair(with_second=True)
    res = solve_maxwell(labels, method="sor", tol=1e-5, extend_grid=False, keep_fields=True)
    assert res.phi is not None and res.phi.shape[0] == 2
    assert res.conductor_ids == [1, 2]
    assert set(res.W) >= {0, 1}
    assert res.warnings == []


FLOAT = MaterialRecord(rgb=(0, 255, 255), use="float", name="floater")
DS = MaterialRecord(
    rgb=(200, 200, 100),
    use="insul",
    er=4.0,
    tan_delta=0.02,
    name="ds-laminate",
    resistivity_ohm_cm=1e6,
    ds_params=DSParams(eps_inf=3.6, delta_eps=0.9, f1_hz=1e3, f2_hz=1e12),
)


def _shielded_map(
    *,
    floater: bool = False,
    unlabelled: bool = False,
    vacuum_gap: bool = False,
) -> Usermap:
    """A small box: ground top and bottom, one signal strip, optional extras."""
    h, w = 24, 40
    mats = [CU, FR4, FLOAT]
    mat = np.full((h, w), 1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[0, :] = 0
    cid[0, :] = 0
    mat[h - 1, :] = 0
    cid[h - 1, :] = 0
    mat[11:13, 8:16] = 0
    cid[11:13, 8:16] = 1
    if floater:
        mat[11:13, 24:32] = 2
        cid[11:13, 24:32] = -2
    if unlabelled:
        mat[6:8, 24:32] = 0  # copper, but left at conductor_ids == -1
    if vacuum_gap:
        mat[17:19, 4:36] = -1  # no material at all: the vacuum bucket
    return Usermap.from_labels(mat, mats, pixel_width_m=2e-5, conductor_ids=cid)


def test_float_group_stays_equipotential() -> None:
    res = solve_maxwell(
        _shielded_map(floater=True), method="sor", tol=1e-7, extend_grid=False, keep_fields=True
    )
    assert res.phi is not None
    group = _shielded_map(floater=True).conductor_ids == -2
    v_float = res.phi[0][group]
    assert float(np.ptp(v_float)) < 1e-12
    assert 0.0 < float(v_float[0]) < 1.0  # it floats to something, not to the BC values
    assert [w.code for w in res.warnings] == []


def test_amg_path_warns_that_float_groups_are_ignored() -> None:
    res = solve_maxwell(
        _shielded_map(floater=True), method="amg", tol=1e-7, extend_grid=False, max_iter=50
    )
    assert "float_groups_ignored_by_amg" in [w.code for w in res.warnings]


def test_no_float_group_no_amg_warning() -> None:
    res = solve_maxwell(_shielded_map(), method="amg", tol=1e-7, extend_grid=False, max_iter=50)
    assert "float_groups_ignored_by_amg" not in [w.code for w in res.warnings]


def test_unlabelled_conductor_pixels_warn() -> None:
    res = solve_maxwell(_shielded_map(unlabelled=True), method="sor", extend_grid=False, tol=1e-5)
    warned = [w for w in res.warnings if w.code == "unlabelled_conductor_pixels"]
    assert len(warned) == 1
    assert "16 conductor pixel(s)" in warned[0].message


def test_vacuum_bucket_is_its_own_material_key() -> None:
    res = solve_maxwell(_shielded_map(vacuum_gap=True), method="sor", extend_grid=False, tol=1e-5)
    assert -1 in res.W
    assert res.W[-1][0, 0] > 0.0


def test_no_signal_conductor_raises() -> None:
    h, w = 12, 12
    mat = np.full((h, w), 1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[0, :] = 0
    cid[0, :] = 0
    um = Usermap.from_labels(mat, [CU, FR4], pixel_width_m=2e-5, conductor_ids=cid)
    with pytest.raises(ValueError, match="no signal conductors"):
        solve_maxwell(um, method="sor", extend_grid=False)


def test_dispersive_material_reference_frequency() -> None:
    h, w = 24, 40
    mat = np.full((h, w), 1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[0, :] = 0
    cid[0, :] = 0
    mat[h - 1, :] = 0
    cid[h - 1, :] = 0
    mat[11:13, 8:16] = 0
    cid[11:13, 8:16] = 1
    um = Usermap.from_labels(mat, [CU, DS], pixel_width_m=2e-5, conductor_ids=cid)

    res = solve_maxwell(um, f_ref_hz=1e9, method="sor", tol=1e-6, extend_grid=False)
    c_lo, g_lo, _ = rlgc_matrices(res, 1e8)
    c_hi, g_hi, _ = rlgc_matrices(res, 1e10)
    assert c_lo[0, 0] > c_hi[0, 0] > 0.0  # Djordjevic-Sarkar er' falls with frequency
    assert g_lo[0, 0] > 0.0 and g_hi[0, 0] > g_lo[0, 0]

    nominal = solve_maxwell(um, method="sor", tol=1e-6, extend_grid=False)
    c_nom, _, _ = rlgc_matrices(nominal, 1e9)
    c_ref, _, _ = rlgc_matrices(res, 1e9)
    assert c_ref[0, 0] == pytest.approx(c_nom[0, 0], rel=0.2)


def test_vacuum_only_reproduces_c0_and_refuses_rlgc() -> None:
    """The vacuum set is the same solve either way, so C0 must match bit for bit."""
    labels, _ = stripline_pair(with_second=True)
    full = solve_maxwell(labels, method="sor", tol=1e-6, extend_grid=True)
    vac = solve_maxwell(labels, method="sor", tol=1e-6, extend_grid=True, vacuum_only=True)
    np.testing.assert_array_equal(vac.C0, full.C0)
    np.testing.assert_array_equal(vac.W0, full.W0)
    assert vac.W == {}
    assert vac.phi is None
    # Half the Laplace solves: the dielectric set is not run at all.
    assert len(vac.iterations) * 2 == len(full.iterations)
    assert vac.pixel_width_m == full.pixel_width_m == labels.pixel_width_m
    with pytest.raises(ValueError, match="vacuum_only"):
        rlgc_matrices(vac, 1e9)
