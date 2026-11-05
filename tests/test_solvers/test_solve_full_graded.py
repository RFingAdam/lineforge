"""solve_full on realistic PCB cross-sections: speed, memory and accuracy.

Regression: a 0.1 mm microstrip on 69 um FR-4
rasterized at 5 um took ~260 s through the uniform-grid C/Gp path (and the
default resolution 512 s with ~0.9 GB traced, reading Z0 = 65 ohm against
~53 ohm); the edge-coupled pair and the asymmetric stripline at 5 um, and the
microstrip at 12 um, ran past 10 minutes. The dense PEEC path could also try
to allocate an N x N int64 index array (``sp.csr_matrix`` of a dense matrix)
for an 18k-pixel map and die with MemoryError.

The graded-mesh solver must do each of these in seconds with bounded memory
and agree with the closed forms that are themselves validated in
``tests/test_analytical/test_closed_form_regressions.py``.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
import tracemalloc
from typing import Any

import numpy as np
import pytest

from lineforge.analytical.hammerstad import hj_static, kirschning_jansen, pucel_r_per_m
from lineforge.analytical.wadell import wheeler_stripline_z0
from lineforge.geometry import from_dict
from lineforge.geometry.builders import auto_pixel_width, rasterize
from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.solvers.faraday import SolverBudgetExceeded
from lineforge.solvers.faraday import solve_lrs as faraday_solve_lrs
from lineforge.solvers.graded import MeshBudgetExceeded, build_mesh
from lineforge.solvers.lrs import solve_full

MS = {"type": "microstrip", "W": "0.1mm", "H": "69um", "T": "35um", "er": 4.2, "tan_delta": 0.02}
DIFF = {
    "type": "edge_coupled_diff_microstrip",
    "W": "0.1mm",
    "S": "0.1mm",
    "H": "69um",
    "T": "35um",
    "er": 4.2,
}
ASYM = {
    "type": "stripline_asymmetric",
    "W": "0.1mm",
    "T": "18um",
    "H1": "89um",
    "H2": "135um",
    "er": 4.2,
}


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLC3_NO_CACHE", "1")


def _timed_full(d: dict[str, Any], px: float | None, **kw: Any) -> tuple[Any, float, float]:
    geom = from_dict(d)
    um = rasterize(geom, pixel_width=px if px is not None else auto_pixel_width(geom))
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        res = solve_full(um, frequency_hz=1e9, **kw)
    finally:
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return res, time.perf_counter() - t0, peak / 1e6


class TestRealisticCrossSections:
    def test_microstrip_5um_fast_bounded_and_accurate(self) -> None:
        res, dt, peak_mb = _timed_full(MS, 5e-6)
        z_ref, eps_ref = hj_static(100e-6, 69e-6, 35e-6, 4.2)
        assert dt < 30.0
        assert peak_mb < 500.0
        assert res.z0_real == pytest.approx(z_ref, rel=0.04)
        assert res.eps_eff == pytest.approx(eps_ref, rel=0.03)
        assert res.method == "graded-fd+perturbation"

    def test_microstrip_12um_does_not_hang(self) -> None:
        res, dt, _ = _timed_full(MS, 12e-6)
        assert dt < 30.0
        z_ref, _ = hj_static(100e-6, 69e-6, 35e-6, 4.2)
        assert res.z0_real == pytest.approx(z_ref, rel=0.10)  # 3 px across T: coarse

    def test_microstrip_default_resolution(self) -> None:
        res, dt, peak_mb = _timed_full(MS, None)
        z_ref, _ = hj_static(100e-6, 69e-6, 35e-6, 4.2)
        assert dt < 30.0
        assert peak_mb < 500.0
        # z0_real includes the skin-effect internal inductance (~+1.3 % at 1 GHz)
        # that the static Hammerstad-Jensen value leaves out.
        assert res.z0_real == pytest.approx(z_ref, rel=0.04)

    def test_edge_coupled_pair_5um(self) -> None:
        res, dt, _ = _timed_full(DIFF, 5e-6)
        _, z_odd, _, eps_odd = kirschning_jansen(100e-6, 100e-6, 69e-6, 35e-6, 4.2)
        assert dt < 30.0
        # +1/-1 drive with a ground plane: Z is the differential impedance.
        assert res.z0_real == pytest.approx(2.0 * z_odd, rel=0.04)
        assert res.eps_eff == pytest.approx(eps_odd, rel=0.04)

    def test_asymmetric_stripline_5um(self) -> None:
        res, dt, _ = _timed_full(ASYM, 5e-6)
        z1 = wheeler_stripline_z0(100e-6, 18e-6, 2 * 89e-6 + 18e-6, 1.0)
        z2 = wheeler_stripline_z0(100e-6, 18e-6, 2 * 135e-6 + 18e-6, 1.0)
        z_ref = 2.0 * z1 * z2 / (z1 + z2) / math.sqrt(4.2)
        assert dt < 30.0
        assert res.z0_real == pytest.approx(z_ref, rel=0.03)
        assert res.eps_eff == pytest.approx(4.2, rel=1e-6)


class TestConductorLoss:
    def test_r_matches_pucel_at_skin_depth_resolution(self) -> None:
        """Perturbational R vs Pucel at 2.45 GHz (delta = 1.3 um, pixel 2.5 um)."""
        d = dict(MS, W="0.104mm")
        um = rasterize(from_dict(d), pixel_width=2.5e-6)
        res = solve_full(um, frequency_hz=2.45e9)
        rs = math.sqrt(math.pi * 2.45e9 * 4e-7 * math.pi * 1.7241e-8)
        assert res.R_per_m == pytest.approx(pucel_r_per_m(104e-6, 69e-6, 35e-6, rs), rel=0.12)

    def test_roughness_raises_r(self) -> None:
        from lineforge.materials.database import RoughnessSpec

        um = rasterize(from_dict(MS), pixel_width=5e-6)
        smooth = solve_full(um, frequency_hz=5e9)
        rough = solve_full(
            um, frequency_hz=5e9, roughness=RoughnessSpec(model="hammerstad", rms_um=1.0)
        )
        assert rough.R_per_m > 1.3 * smooth.R_per_m


class TestMemoryGuards:
    def _big_microstrip(self) -> Usermap:
        return rasterize(from_dict(MS), pixel_width=0.5e-6)  # ~100k-pixel bitmap

    def test_auto_coarsen_stays_in_budget(self) -> None:
        um = self._big_microstrip()
        res = solve_full(um, frequency_hz=1e9, max_cells=20_000)
        assert res.n_mesh_cells is not None and res.n_mesh_cells <= 20_000
        assert res.pixel_width_m is not None and res.pixel_width_m > um.pixel_width_m
        assert any(w.code == "auto_coarsened" for w in res.warnings)
        z_ref, _ = hj_static(100e-6, 69e-6, 35e-6, 4.2)
        assert res.z0_real == pytest.approx(z_ref, rel=0.06)

    def test_budget_refusal_is_a_clear_error(self) -> None:
        with pytest.raises(MeshBudgetExceeded, match="budget"):
            build_mesh(self._big_microstrip(), max_cells=20_000, auto_coarsen=False)

    def test_dense_peec_refuses_instead_of_allocating(self) -> None:
        """An 18k-conductor-pixel map must be refused before any N^2 allocation."""
        rgb = np.full((140, 300, 3), 255, dtype=np.uint8)
        rgb[10:40, :] = (255, 0, 0)  # 9000 px
        rgb[100:130, :] = (0, 255, 0)  # 9000 px
        um = Usermap(rgb, UsermapMetadata(pixel_width_m=5e-6))
        t0 = time.perf_counter()
        with pytest.raises(SolverBudgetExceeded, match="dense PEEC budget"):
            faraday_solve_lrs(um, frequency_hz=1e9)
        assert time.perf_counter() - t0 < 5.0


def _structured(call_result: Any) -> dict[str, Any]:
    if call_result.structured_content:
        return dict(call_result.structured_content)
    return dict(json.loads(call_result.content[0].text))


@pytest.mark.asyncio
async def test_mcp_solve_full_geometry_default_resolution() -> None:
    """The MCP tool with a geometry and no pixel_width completes quickly and correctly."""
    from lineforge.mcp_server.server import build_server

    server = build_server()
    out = _structured(await server.call_tool("solve_full", {"geometry": MS, "frequency": "1GHz"}))
    task_id = out["taskId"]
    for _ in range(120):
        await asyncio.sleep(0.25)
        status = _structured(await server.call_tool("tasks_get", {"task_id": task_id}))
        if status["status"] in ("completed", "failed"):
            break
    assert status["status"] == "completed", status
    result = status["result"]
    z_ref, _ = hj_static(100e-6, 69e-6, 35e-6, 4.2)
    assert result["z0_real"] == pytest.approx(z_ref, rel=0.04)
    assert result["method"] == "graded-fd+perturbation"
