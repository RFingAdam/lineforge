"""Closed-form model regressions on typical multilayer-PCB cross-sections.

Geometries used: 69 um dielectric to a plane for microstrip, 89 um / 135 um
dielectrics either side of a stripline, er 4.2, copper 18-35 um, widths
0.08-0.30 mm. Reference
values come from the graded-mesh field solver (``lineforge.solvers.graded``),
which is itself checked here against Wheeler's stripline formula (0.5 %
stated accuracy) so the references are not circular.
"""

from __future__ import annotations

import itertools
import math
import warnings
from typing import Any, ClassVar

import numpy as np
import pytest

from lineforge.analytical import solve
from lineforge.analytical._constants import C0
from lineforge.analytical.hammerstad import pucel_r_per_m
from lineforge.analytical.wadell import wheeler_stripline_z0
from lineforge.geometry import from_dict
from lineforge.geometry.builders import rasterize
from lineforge.geometry.usermap import Usermap
from lineforge.solvers.graded import build_mesh, solve_mesh

ER = 4.2


def _g(**kw: object) -> object:
    return from_dict(dict(kw))


def _solve(**kw: object):  # type: ignore[no-untyped-def]
    freq = kw.pop("_f", None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return solve(from_dict(dict(kw)), frequency_hz=freq)


def _fd(usermap: Usermap) -> tuple[float, float]:
    """(Z0, eps_eff) of a +1-vs-ground usermap from the graded field solver."""
    mesh = build_mesh(usermap)
    c = solve_mesh(mesh).charges
    cv = solve_mesh(mesh, vacuum=True).charges
    q, qv = c.q[c.label == 1].sum(), cv.q[cv.label == 1].sum()
    return 1.0 / (C0 * math.sqrt(q * qv)), q / qv


def _fd_geom(d: dict[str, object], px: float) -> tuple[float, float]:
    return _fd(rasterize(from_dict(d), pixel_width=px))


def _fd_pair(d: dict[str, object], px: float) -> dict[str, float]:
    um = rasterize(from_dict(d), pixel_width=px)
    z_odd, e_odd = _fd(um)
    rgb = um.rgb.copy()
    rgb[(rgb == np.array([0, 0, 255], np.uint8)).all(-1)] = (255, 0, 0)
    z_even2, e_even = _fd(Usermap(rgb, um.meta, material_lookup=um.material_lookup))
    return {"z_odd": z_odd, "z_even": 2.0 * z_even2, "eps_odd": e_odd, "eps_even": e_even}


class TestFieldSolverReference:
    def test_graded_solver_matches_wheeler_stripline(self) -> None:
        d = {"type": "stripline_symmetric", "W": 88e-6, "T": 35e-6, "B": 212e-6, "er": ER}
        z, eps = _fd_geom(d, 1.75e-6)
        assert eps == pytest.approx(ER, rel=1e-9)
        assert z == pytest.approx(wheeler_stripline_z0(88e-6, 35e-6, 212e-6, ER), rel=0.01)


# --------------------------------------------------------------------------- defect 2
class TestCoupledMicrostrip:
    PAIR: ClassVar[dict[str, Any]] = {
        "type": "edge_coupled_diff_microstrip",
        "W": 100e-6,
        "S": 100e-6,
        "H": 69e-6,
        "T": 35e-6,
        "er": ER,
    }

    def test_odd_mode_eps_eff_below_even(self) -> None:
        r = _solve(**self.PAIR)
        assert r.eps_eff_odd < r.eps_eff_even - 0.3
        assert r.vp_odd > r.vp_even
        assert r.method.startswith("kirschning-jansen")
        assert r.model_accuracy

    def test_matches_field_solver(self) -> None:
        r = _solve(**self.PAIR)
        fd = _fd_pair(self.PAIR, 35e-6 / 6)
        assert r.z_odd == pytest.approx(fd["z_odd"], rel=0.02)
        assert r.z_even == pytest.approx(fd["z_even"], rel=0.02)
        assert r.eps_eff_odd == pytest.approx(fd["eps_odd"], rel=0.04)
        assert r.eps_eff_even == pytest.approx(fd["eps_even"], rel=0.02)

    def test_solder_mask_lowers_impedance_odd_mode_most(self) -> None:
        bare = _solve(**self.PAIR)
        masked = _solve(**self.PAIR, mask_thickness=20e-6, mask_er=3.5)
        assert masked.eps_eff_odd > bare.eps_eff_odd
        assert masked.eps_eff_even > bare.eps_eff_even
        assert masked.z_odd / bare.z_odd < masked.z_even / bare.z_even < 1.0
        # Field-solved ratios for this pair with a 20 um, er 3.5 mask:
        # Z_odd x0.901, Z_even x0.9445.
        assert masked.z_odd / bare.z_odd == pytest.approx(0.901, abs=0.012)
        assert masked.z_even / bare.z_even == pytest.approx(0.9445, abs=0.012)

    def test_mask_on_single_microstrip(self) -> None:
        ms = {"type": "microstrip", "W": 100e-6, "H": 69e-6, "T": 35e-6, "er": ER}
        bare = _solve(**ms)
        masked = _solve(**ms, mask_thickness=20e-6, mask_er=3.5)
        assert masked.z0 / bare.z0 == pytest.approx(0.9282, abs=0.012)  # field solve
        assert "solder-mask" in masked.method


# --------------------------------------------------------------------------- defect 3
class TestStriplineModels:
    @pytest.mark.parametrize(
        ("W", "fd_z0"),
        [(304.8e-6, 22.43), (89e-6, 44.70)],  # graded-mesh field solves, T = 35 um
    )
    def test_asymmetric_matches_field_solve(self, W: float, fd_z0: float) -> None:
        r = _solve(type="stripline_asymmetric", W=W, T=35e-6, H1=89e-6, H2=135e-6, er=ER)
        assert r.z0 == pytest.approx(fd_z0, rel=0.03)
        assert r.model_accuracy is not None and "Wheeler" in r.model_accuracy

    @pytest.mark.parametrize("W", [304.8e-6, 150e-6, 89e-6])
    def test_symmetric_matches_field_solve(self, W: float) -> None:
        d = {"type": "stripline_symmetric", "W": W, "T": 18e-6, "B": 196e-6, "er": ER}
        r = _solve(**d)
        z_fd, _ = _fd_geom(d, 3e-6)
        assert r.z0 == pytest.approx(z_fd, rel=0.02)
        assert r.method == "wheeler-1978-stripline"

    def test_large_offset_warns_and_states_error(self) -> None:
        r = _solve(type="stripline_asymmetric", W=89e-6, T=18e-6, H1=40e-6, H2=400e-6, er=ER)
        codes = [w.code for w in r.warnings]
        assert "validity_offset" in codes
        assert r.model_accuracy is not None and "h_far/h_near=10" in r.model_accuracy

    def test_thick_strip_warns(self) -> None:
        r = _solve(type="stripline_symmetric", W=100e-6, T=70e-6, B=200e-6, er=ER)
        assert any(w.code == "out_of_range" for w in r.warnings)

    def test_mcp_exposes_validity_warnings(self) -> None:
        import asyncio
        import json

        from lineforge.mcp_server.server import build_server

        async def _call() -> dict[str, object]:
            server = build_server()
            res = await server.call_tool(
                "calculate_impedance",
                {
                    "geometry": {
                        "type": "stripline_asymmetric",
                        "W": "89um",
                        "T": "18um",
                        "H1": "40um",
                        "H2": "400um",
                        "er": ER,
                    }
                },
            )
            if res.structured_content:
                return dict(res.structured_content)
            return dict(json.loads(res.content[0].text))

        out = asyncio.run(_call())
        assert out["validity_warnings"]


# --------------------------------------------------------------------------- defect 4
class TestDielectricLossConsistency:
    GEOM: ClassVar[dict[str, Any]] = {
        "W": 100e-6,
        "H": 69e-6,
        "T": 18e-6,
        "er": ER,
        "tan_delta": 0.02,
    }

    def test_embedded_not_below_bare_with_default_coating_df(self) -> None:
        bare = _solve(type="microstrip", **self.GEOM, _f=1e9)
        emb = _solve(type="embedded_microstrip", **self.GEOM, H2=20e-6, er2=ER, _f=1e9)
        assert emb.dielectric_loss_db_per_in >= bare.dielectric_loss_db_per_in

    def test_ordering_microstrip_embedded_stripline(self) -> None:
        bare = _solve(type="microstrip", **self.GEOM, _f=1e9)
        thin = _solve(type="embedded_microstrip", **self.GEOM, H2=20e-6, er2=ER, _f=1e9)
        thick = _solve(type="embedded_microstrip", **self.GEOM, H2=2e-3, er2=ER, _f=1e9)
        strip = _solve(
            type="stripline_symmetric", W=100e-6, T=18e-6, B=200e-6, er=ER, tan_delta=0.02, _f=1e9
        )
        losses = [
            bare.dielectric_loss_db_per_in,
            thin.dielectric_loss_db_per_in,
            thick.dielectric_loss_db_per_in,
        ]
        assert losses == sorted(losses)
        # A fully buried line has the stripline loss: alpha = pi f sqrt(er) tan / c.
        assert thick.eps_eff <= ER
        assert thick.dielectric_loss_db_per_in == pytest.approx(
            strip.dielectric_loss_db_per_in, rel=0.03
        )

    def test_lossless_coating_lowers_loss_only_by_filling(self) -> None:
        lossy = _solve(type="embedded_microstrip", **self.GEOM, H2=20e-6, er2=ER, _f=1e9)
        free = _solve(
            type="embedded_microstrip", **self.GEOM, H2=20e-6, er2=ER, tan_delta_2=0.0, _f=1e9
        )
        assert free.dielectric_loss_db_per_in < lossy.dielectric_loss_db_per_in

    def test_embedded_matches_field_solve(self) -> None:
        d = {
            "type": "embedded_microstrip",
            "W": 100e-6,
            "H": 69e-6,
            "T": 18e-6,
            "H2": 20e-6,
            "er": ER,
            "er2": ER,
        }
        z_fd, e_fd = _fd_geom(d, 3e-6)
        r = _solve(**d)
        assert r.z0 == pytest.approx(z_fd, rel=0.03)
        assert r.eps_eff == pytest.approx(e_fd, rel=0.03)


# --------------------------------------------------------------------------- defect 6
class TestCPWG:
    BASE: ClassVar[dict[str, Any]] = {
        "type": "cpwg",
        "W": 104.1e-6,
        "H": 69e-6,
        "T": 35e-6,
        "er": ER,
    }

    def test_never_above_microstrip(self) -> None:
        ms = _solve(type="microstrip", W=104.1e-6, H=69e-6, T=35e-6, er=ER)
        r = _solve(**self.BASE, S=260e-6)
        assert r.z0 <= ms.z0
        assert r.z0 == pytest.approx(ms.z0, rel=0.02)

    def test_monotonic_in_gap(self) -> None:
        ms = _solve(type="microstrip", W=104.1e-6, H=69e-6, T=35e-6, er=ER)
        gaps = [10e-6, 25e-6, 50e-6, 100e-6, 200e-6, 400e-6, 1e-3, 5e-3]
        z = [_solve(**self.BASE, S=s).z0 for s in gaps]
        assert all(b > a for a, b in itertools.pairwise(z))
        assert max(z) <= ms.z0 + 1e-9

    @pytest.mark.parametrize("S", [25e-6, 50e-6, 100e-6, 260e-6])
    def test_matches_field_solve(self, S: float) -> None:
        d = dict(self.BASE, S=S)
        z_fd, _ = _fd_geom(d, min(35e-6 / 6, S / 10))
        assert _solve(**d).z0 == pytest.approx(z_fd, rel=0.035)


# --------------------------------------------------------------------------- defect 7
class TestMicrostripConductorLoss:
    LINE: ClassVar[dict[str, Any]] = {
        "type": "microstrip",
        "W": 104e-6,
        "H": 69e-6,
        "T": 35e-6,
        "er": ER,
    }

    def test_skin_effect_loss_at_2g45(self) -> None:
        r = _solve(**self.LINE, _f=2.45e9)
        rs = math.sqrt(math.pi * 2.45e9 * 4e-7 * math.pi * 1.7241e-8)  # ~12.9 mohm/sq
        r_pucel = pucel_r_per_m(104e-6, 69e-6, 35e-6, rs)
        expected = r_pucel / (2 * r.z0) * 8.685889638 * 0.0254
        # rel 1 %: the DC resistance is folded in as sqrt(Rdc^2 + Rac^2)
        assert r.conductor_loss_db_per_in == pytest.approx(expected, rel=0.01)
        assert 0.12 < r.conductor_loss_db_per_in < 0.25  # ~0.16 dB/in smooth copper
        # Cross-check the closed form against the field solver's surface-impedance R.
        from lineforge.solvers.lrs import solve_full

        fd = solve_full(rasterize(from_dict(self.LINE), pixel_width=2.5e-6), frequency_hz=2.45e9)
        assert r_pucel == pytest.approx(fd.R_per_m, rel=0.12)

    def test_loss_scales_with_sqrt_f(self) -> None:
        a = _solve(**self.LINE, _f=1e9).conductor_loss_db_per_in
        b = _solve(**self.LINE, _f=4e9).conductor_loss_db_per_in
        assert b / a == pytest.approx(2.0, rel=0.03)

    def test_roughness(self) -> None:
        from lineforge.solvers.roughness import hammerstad_factor

        smooth = _solve(**self.LINE, _f=2.45e9).conductor_loss_db_per_in
        rough = _solve(
            **self.LINE, roughness={"model": "hammerstad", "rms_um": 1.0}, _f=2.45e9
        ).conductor_loss_db_per_in
        delta = math.sqrt(1.7241e-8 / (math.pi * 2.45e9 * 4e-7 * math.pi))
        assert rough / smooth == pytest.approx(hammerstad_factor(delta, 1e-6), rel=0.01)


# --------------------------------------------------------------------------- defect 5
class TestSilentErrors:
    def test_thick_microstrip_eps_eff(self) -> None:
        """HJ's thickness correction lowers eps_eff; it used to raise it (3.18 vs 2.86)."""
        d = {"type": "microstrip", "W": 100e-6, "H": 69e-6, "T": 35e-6, "er": ER}
        z_fd, e_fd = _fd_geom(d, 35e-6 / 8)
        r = _solve(**d)
        assert r.eps_eff == pytest.approx(e_fd, rel=0.02)
        assert r.z0 == pytest.approx(z_fd, rel=0.03)

    def test_rasterizer_keeps_exact_er(self) -> None:
        """er = 4.2 used to be snapped to the nearest atlc2 colour (PVC, er 4.5, tan 0.011)."""
        um = rasterize(_g(type="microstrip", W=1e-4, H=69e-6, T=35e-6, er=ER, tan_delta=0.02))
        er = um.er_field()
        assert set(np.unique(er)) == {1.0, ER}
        assert set(np.unique(um.tan_delta_field())) == {0.0, 0.02}

    def test_cache_key_covers_materials(self) -> None:
        from lineforge.cache import _hash_args

        a = rasterize(
            _g(
                type="stripline_asymmetric",
                W=1e-4,
                T=18e-6,
                H1=89e-6,
                H2=135e-6,
                er=4.20,
                er_above=4.20,
                er_below=3.70,
            )
        )
        b = rasterize(
            _g(
                type="stripline_asymmetric",
                W=1e-4,
                T=18e-6,
                H1=89e-6,
                H2=135e-6,
                er=4.21,
                er_above=4.21,
                er_below=3.70,
            )
        )
        assert np.array_equal(a.rgb, b.rgb)  # same synthesized colours ...
        assert _hash_args((a,), {}) != _hash_args((b,), {})  # ... different materials

    def test_embedded_eps_eff_bounded_by_er(self) -> None:
        r = _solve(type="embedded_microstrip", W=1e-4, H=69e-6, T=18e-6, H2=1e-3, er=ER, er2=ER)
        assert r.eps_eff <= ER + 1e-9
