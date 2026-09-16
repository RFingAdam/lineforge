"""Maxwell capacitance matrices reduce to the existing single-line and differential solvers."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap
from lineforge.materials.database import MaterialRecord
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
    assert C[0, 1] == pytest.approx(C[1, 0], rel=1e-6)
    assert C[0, 1] < 0 < C[0, 0]
    modes = diff_modes.solve_modes(roles)
    c_odd = C[0, 0] - C[0, 1]
    c_even = C[0, 0] + C[0, 1]
    z_odd = np.sqrt((L[0, 0] - L[0, 1]) / c_odd)
    z_even = np.sqrt((L[0, 0] + L[0, 1]) / c_even)
    assert z_odd == pytest.approx(modes.z_odd, rel=3e-3)
    assert z_even == pytest.approx(modes.z_even, rel=3e-3)
    eig = np.linalg.eigvalsh(C)
    assert (eig > 0).all()


def test_keep_fields_and_warnings_shape() -> None:
    labels, _ = stripline_pair(with_second=True)
    res = solve_maxwell(labels, method="sor", tol=1e-5, extend_grid=False, keep_fields=True)
    assert res.phi is not None and res.phi.shape[0] == 2
    assert res.conductor_ids == [1, 2]
    assert set(res.W) >= {0, 1}
