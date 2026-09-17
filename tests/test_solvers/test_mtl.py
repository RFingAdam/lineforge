"""Maxwell capacitance matrices reduce to the existing single-line and differential solvers."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.analytical._constants import EPS0, MU0
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
    assert L[0, 0] == pytest.approx(ref.L_per_m, rel=2e-3)
    # cgp still books a one-pixel rim of dielectric energy at er = 1, so C and G
    # sit below this solver by the conductor perimeter-to-area ratio. L is vacuum
    # and is unaffected.
    assert C[0, 0] == pytest.approx(ref.C_per_m, rel=0.15)
    assert G[0, 0] == pytest.approx(ref.Gp_per_m, rel=0.15)


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
    # solve_modes uses the same rim booking as cgp, so odd/even Z0 sit high of
    # the Maxwell matrices by about the perimeter-to-area ratio. The sign of
    # coupling and the row sums are the checks that do not inherit that bias.
    assert z_odd == pytest.approx(modes.z_odd, rel=0.08)
    assert z_even == pytest.approx(modes.z_even, rel=0.08)
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


HOMOGENEOUS_ER = 4.3
HOMOGENEOUS_FILL = MaterialRecord(
    rgb=(223, 247, 136),
    use="insul",
    er=HOMOGENEOUS_ER,
    tan_delta=0.0,
    name="homogeneous-fill",
    resistivity_ohm_cm=1e6,
)
AIR = MaterialRecord(
    rgb=(0, 0, 0),
    use="insul",
    er=1.0,
    tan_delta=0.0,
    name="air",
    resistivity_ohm_cm=1e6,
)


def _homogeneous_pair(pixel_width_m: float, *, scale: int = 1) -> Usermap:
    """Two traces over a plane in a uniform dielectric, scaled in pixel count.

    Physical size is held fixed as ``scale`` grows and ``pixel_width_m`` shrinks, so a
    booking bug that scales with the conductor perimeter-to-area ratio would still
    show up across the three sizes.
    """
    h, w = 24 * scale, 48 * scale
    mat = np.full((h, w), 1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    plane = 2 * scale
    mat[h - plane : h, :] = 0
    cid[h - plane : h, :] = 0
    t_h, t_w, t_y = 2 * scale, 6 * scale, 8 * scale
    mat[t_y : t_y + t_h, 8 * scale : 8 * scale + t_w] = 0
    cid[t_y : t_y + t_h, 8 * scale : 8 * scale + t_w] = 1
    mat[t_y : t_y + t_h, 34 * scale : 34 * scale + t_w] = 0
    cid[t_y : t_y + t_h, 34 * scale : 34 * scale + t_w] = 2
    return Usermap.from_labels(
        mat, [CU, HOMOGENEOUS_FILL], pixel_width_m=pixel_width_m, conductor_ids=cid
    )


@pytest.mark.parametrize(
    ("pixel_width_m", "scale"),
    [
        (50.0e-6, 1),
        (25.0e-6, 2),
        (50.0e-6 / 3.0, 3),
    ],
)
def test_homogeneous_fill_books_no_energy_on_the_conductor(pixel_width_m: float, scale: int) -> None:
    """A uniform fill returns C = er C0, so L C / (mu0 eps0) is er and W on copper is empty."""
    um = _homogeneous_pair(pixel_width_m, scale=scale)
    res = solve_maxwell(um, method="sor", tol=1e-7, extend_grid=False)
    c, _, l_ext = rlgc_matrices(res, 1e9)
    product = (l_ext @ c) / (MU0 * EPS0)
    np.testing.assert_allclose(product, HOMOGENEOUS_ER * np.eye(2), rtol=0.0, atol=1e-6)
    copper = res.W[0]
    assert float(np.max(np.abs(copper))) < 1e-9
    w_diag = sum(float(w[0, 0]) for w in res.W.values())
    assert w_diag > 0.0
    assert abs(float(res.W[0][0, 0]) / w_diag) < 1e-9


def test_mixed_dielectric_partitions_energy_between_the_dielectrics() -> None:
    """Substrate under, air above: both dielectrics carry W, the shares sum to 1, copper is empty."""
    h, w = 24, 48
    # 0 copper, 1 substrate, 2 air
    mat = np.full((h, w), 2, dtype=np.int32)
    mat[h // 2 :, :] = 1
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[h - 2 : h, :] = 0
    cid[h - 2 : h, :] = 0
    mat[h // 2 - 2 : h // 2, 16:24] = 0
    cid[h // 2 - 2 : h // 2, 16:24] = 1
    um = Usermap.from_labels(
        mat, [CU, HOMOGENEOUS_FILL, AIR], pixel_width_m=25e-6, conductor_ids=cid
    )
    res = solve_maxwell(um, method="sor", tol=1e-7, extend_grid=False)
    w00 = {m: float(w[0, 0]) for m, w in res.W.items()}
    total = sum(w00.values())
    assert total > 0.0
    assert abs(w00[0]) < 1e-9
    diel = sum(v for k, v in w00.items() if k != 0)
    assert diel / total == pytest.approx(1.0, abs=1e-12)
    assert w00[1] > 0.0
    assert w00[2] > 0.0
