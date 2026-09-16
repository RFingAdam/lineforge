"""The N-conductor PEEC impedance matrix reduces to solve_lrs for one conductor and is symmetric for pairs."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.materials.database import MaterialRecord
from lineforge.solvers import faraday
from lineforge.solvers.faraday import SolverBudgetExceeded, solve_impedance_matrix

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
GND = MaterialRecord(rgb=(0, 255, 0), use="0", name="ground")


def small_pair(second: bool) -> tuple[Usermap, Usermap]:
    """Build the label map (and its RGB-role twin) for a 16x40 microstrip cross-section."""
    h, w = 16, 40
    mat = np.full((h, w), -1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[14:16, :] = 0
    cid[14:16, :] = 0
    mat[4:6, 8:14] = 0
    cid[4:6, 8:14] = 1
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)
    rgb[14:16, :] = GND.rgb
    rgb[4:6, 8:14] = CU.rgb
    if second:
        mat[4:6, 26:32] = 0
        cid[4:6, 26:32] = 2
    labels = Usermap.from_labels(mat, [CU], pixel_width_m=2e-5, conductor_ids=cid)
    roles = Usermap(rgb, UsermapMetadata(pixel_width_m=2e-5), unknown_warning=False)
    return labels, roles


def test_single_conductor_equals_solve_lrs() -> None:
    labels, roles = small_pair(second=False)
    r_mat, l_mat = solve_impedance_matrix(labels, frequency_hz=1e8, restrict_to_skin_depth=False)
    ref = faraday.solve_lrs(roles, frequency_hz=1e8)
    assert r_mat.shape == (1, 1)
    assert l_mat.shape == (1, 1)
    assert r_mat[0, 0] == pytest.approx(ref.R_per_m, rel=1e-9)
    assert l_mat[0, 0] == pytest.approx(ref.L_per_m, rel=1e-9)


def test_pair_symmetric_with_positive_mutual() -> None:
    labels, _ = small_pair(second=True)
    r_mat, l_mat = solve_impedance_matrix(labels, frequency_hz=1e8, restrict_to_skin_depth=False)
    assert l_mat.shape == (2, 2)
    assert l_mat[0, 1] == pytest.approx(l_mat[1, 0], rel=1e-6)
    assert 0 < l_mat[0, 1] < l_mat[0, 0]
    assert r_mat[0, 0] == pytest.approx(r_mat[1, 1], rel=1e-6)


def test_budget_refusal() -> None:
    labels, _ = small_pair(second=True)
    with pytest.raises(SolverBudgetExceeded):
        solve_impedance_matrix(
            labels, frequency_hz=1e8, restrict_to_skin_depth=False, max_pixels=10
        )


def test_missing_reference_conductor_is_rejected() -> None:
    labels, _ = small_pair(second=False)
    cid = labels.conductor_ids.copy()
    cid[cid == 0] = 1
    no_ref = Usermap.from_labels(
        labels.codes.astype(np.int32), [CU], pixel_width_m=2e-5, conductor_ids=cid
    )
    with pytest.raises(ValueError, match="reference conductor"):
        solve_impedance_matrix(no_ref, frequency_hz=1e8, restrict_to_skin_depth=False)


def test_skin_masking_preserves_conductor_ids() -> None:
    from lineforge.solvers.skin_depth import mask_skin_depth

    labels, _ = small_pair(second=True)
    # At 10 MHz copper's delta is about one pixel here, so factor 1.5 blackens the
    # pixels two deep (the far side of the 2-pixel ground plane) and nothing else.
    masked = mask_skin_depth(labels, 1e7, factor=1.5)
    assert masked.conductor_ids.shape == labels.conductor_ids.shape
    # Masking only ever removes conductor pixels; it never invents or relabels one.
    kept = masked.conductor_ids >= 0
    assert np.array_equal(masked.conductor_ids[kept], labels.conductor_ids[kept])
    dropped = (labels.conductor_ids >= 0) & (masked.conductor_ids < 0)
    assert dropped.any()
    assert np.all(masked.codes[dropped] == -1)
    # The surviving pixels are exactly what the matrix solver then bills against.
    r_mat, _l_mat = solve_impedance_matrix(labels, frequency_hz=1e7, restrict_to_skin_depth=True)
    assert r_mat.shape == (2, 2)
