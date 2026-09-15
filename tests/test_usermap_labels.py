"""Label-based usermaps carry integer conductor ids and material codes without an RGB round trip."""

from __future__ import annotations

import numpy as np
import pytest

from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.materials.database import MaterialRecord
from lineforge.solvers import extension

CU = MaterialRecord(rgb=(255, 0, 0), use="+1", name="copper")
GND = MaterialRecord(rgb=(0, 255, 0), use="0", name="ground")
FR4 = MaterialRecord(
    rgb=(223, 247, 136), use="insul", er=3.7, tan_delta=0.018, name="FR4", resistivity_ohm_cm=1e6
)
VAC = MaterialRecord(rgb=(255, 255, 255), use="insul", name="vacuum", resistivity_ohm_cm=1e6)


def three_conductor_map() -> Usermap:
    h, w = 20, 40
    mat = np.full((h, w), -1, dtype=np.int32)
    cid = np.full((h, w), -1, dtype=np.int32)
    mat[10:20, :] = 1  # FR4 below
    mat[19, :] = 0  # ground plane row (copper material index 0)
    cid[19, :] = 0
    mat[8:10, 5:12] = 0
    cid[8:10, 5:12] = 1
    mat[8:10, 20:27] = 0
    cid[8:10, 20:27] = 2
    return Usermap.from_labels(mat, [CU, FR4], pixel_width_m=1e-5, conductor_ids=cid)


def test_from_labels_masks_and_fields() -> None:
    u = three_conductor_map()
    assert u.shape == (20, 40)
    assert u.n_signal_conductors == 2
    assert u.conductor_mask(1).sum() == 14
    assert u.conductor_mask(2).sum() == 14
    assert u.conductor_mask(0).sum() == 40
    assert u.conductor_mask(None).sum() == 68
    assert u.er_field()[15, 3] == pytest.approx(3.7)
    assert u.er_field()[2, 2] == pytest.approx(1.0)
    assert u.tan_delta_field()[15, 3] == pytest.approx(0.018)


def test_rgb_map_derives_conductor_ids() -> None:
    rgb = np.full((6, 6, 3), 255, dtype=np.uint8)
    rgb[1, :] = (255, 0, 0)
    rgb[4, :] = (0, 0, 255)
    u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4))
    assert set(np.unique(u.conductor_ids).tolist()) == {-1, 1, 2}
    assert u.conductor_mask("+1").sum() == u.conductor_mask(1).sum() == 6


def test_vectorised_init_matches_reference_loop() -> None:
    rng = np.random.default_rng(0)
    colours = np.array(
        [(255, 0, 0), (0, 0, 255), (0, 255, 0), (223, 247, 136), (255, 255, 255), (7, 7, 7)],
        dtype=np.uint8,
    )
    idx = rng.integers(0, len(colours), size=(50, 70))
    rgb = colours[idx]
    u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-4), unknown_warning=False)
    # reference: slow per-pixel mapping through the same lookup
    seen: dict[tuple[int, int, int], int] = {}
    ref = np.full((50, 70), -1, dtype=np.int16)
    mats = []
    for y in range(50):
        for x in range(70):
            key = tuple(int(v) for v in rgb[y, x])
            if key in seen:
                ref[y, x] = seen[key]
                continue
            m = u.material_lookup.get(key)  # type: ignore[arg-type]
            if m is None:
                continue
            seen[key] = len(mats)  # type: ignore[assignment]
            mats.append(m)
            ref[y, x] = seen[key]  # type: ignore[assignment]
    # material order may differ; compare by material name per pixel
    names_u = np.array([m.name for m in u.materials] + ["vacuum"])[
        np.where(u.codes < 0, len(u.materials), u.codes)
    ]
    names_r = np.array([m.name for m in mats] + ["vacuum"])[np.where(ref < 0, len(mats), ref)]
    assert (names_u == names_r).all()


def test_replicate_and_extend_keep_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    u = three_conductor_map()
    padded = u.replicate_edges(3)
    assert padded.shape == (26, 46)
    assert padded.conductor_mask(1).sum() == 14
    # The ground row (id 0, 40 px wide) replicates into the 3 padded columns on
    # each side (-> 46 px wide) and then down into the 3 padded rows below it,
    # so the ground row itself plus its 3 copies span 46 * 4 = 184 pixels.
    assert padded.conductor_mask(0).sum() == 184
    big = extension.extend_to_shape(u, 40, 80)
    assert big.n_signal_conductors == 2
    assert big.conductor_mask(2).sum() == 14
