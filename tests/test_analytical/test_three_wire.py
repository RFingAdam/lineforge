"""Tests for the closed-form 3-wire Y-decomposition solver."""

from __future__ import annotations

import math

import pytest

from atlc3.analytical.three_wire import solve_three_wire, y_decomposition
from atlc3.geometry.three_wire import ThreeWireGeometry, WirePosition

ETA0 = 376.730313668  # vacuum impedance


class TestYDecompositionAlgebra:
    def test_basic_recovery(self) -> None:
        """The forward + inverse map round-trips: given Y-legs, you can
        compute the three pair impedances, then recover the legs."""
        zo_r, zo_g, zo_b = 30.0, 20.0, 25.0
        z_rcz = zo_g + zo_b
        z_gcz = zo_r + zo_b
        z_bcz = zo_r + zo_g
        r_rec, g_rec, b_rec = y_decomposition(z_rcz, z_gcz, z_bcz)
        assert r_rec == pytest.approx(zo_r, rel=1e-12)
        assert g_rec == pytest.approx(zo_g, rel=1e-12)
        assert b_rec == pytest.approx(zo_b, rel=1e-12)

    def test_symmetric_input_symmetric_output(self) -> None:
        """All three pair impedances equal → all three Y-legs equal to Z_pair/2."""
        zo_r, zo_g, zo_b = y_decomposition(100.0, 100.0, 100.0)
        assert zo_r == zo_g == zo_b == pytest.approx(50.0)


class TestSymmetricGeometry:
    def test_equilateral_above_ground(self) -> None:
        """3 equal wires in equilateral triangle above ground: ZoR == ZoB
        (red and blue are symmetric); ZoG differs because green sits at the
        triangle apex above the others."""
        spacing = 4e-3
        h = 5e-3
        geom = ThreeWireGeometry(
            a="0.5mm",
            red=WirePosition(x=-spacing / 2, y=h),
            blue=WirePosition(x=spacing / 2, y=h),
            green=WirePosition(x=0, y=h + math.sqrt(3) / 2 * spacing),
            er=1.0,
            ground_plane=True,
        )
        r = solve_three_wire(geom)
        assert r.zo_r == pytest.approx(r.zo_b, rel=1e-9)
        assert r.z_rcz == pytest.approx(r.z_bcz, rel=1e-9)
        # Pure-symmetric drive → no radiation
        assert r.ignd_ratio == pytest.approx(0.0, abs=1e-9)
        # Pair impedances are 50–500 Ω class — not 0, not negative
        assert 50 < r.z_rcz < 1000
        assert 50 < r.z_gcz < 1000

    def test_collinear_three_wire_above_ground(self) -> None:
        """Three colinear wires (R—G—B at the same height) should have ZoR=ZoB
        by reflection symmetry."""
        h = 5e-3
        geom = ThreeWireGeometry(
            a="0.5mm",
            red=WirePosition(x=-3e-3, y=h),
            green=WirePosition(x=0, y=h),
            blue=WirePosition(x=3e-3, y=h),
            er=1.0,
            ground_plane=True,
        )
        r = solve_three_wire(geom)
        assert r.zo_r == pytest.approx(r.zo_b, rel=1e-9)


class TestTwoWireLimit:
    """When one conductor is far away, the active-pair impedance should
    match the standard two-wire formula."""

    def test_far_third_wire_matches_2wire_in_air(self) -> None:
        """3-wire with green pushed to ∞ → z_gcz (red+blue active) matches
        Z₀ = (η₀/π) ln(D/a) for thin-wire limit."""
        a = 0.5e-3
        D = 4e-3
        z_2wire = (ETA0 / math.pi) * math.log(D / a)

        geom = ThreeWireGeometry(
            a=a,
            red=WirePosition(x=-D / 2, y=0),
            blue=WirePosition(x=D / 2, y=0),
            green=WirePosition(x=0, y=10.0),  # very far
            er=1.0,
            ground_plane=False,
        )
        r = solve_three_wire(geom)
        assert r.z_gcz == pytest.approx(z_2wire, rel=1e-3)

    def test_dielectric_filled_scales_inversely_with_sqrt_er(self) -> None:
        """Z₀ scales as 1/√εr in uniform dielectric."""
        D = 4e-3
        geom_air = ThreeWireGeometry(
            a="0.5mm",
            red=WirePosition(x=-D / 2, y=0),
            blue=WirePosition(x=D / 2, y=0),
            green=WirePosition(x=0, y=10.0),
            er=1.0,
            ground_plane=False,
        )
        geom_er4 = geom_air.model_copy(update={"er": 4.0})
        r_air = solve_three_wire(geom_air)
        r_er4 = solve_three_wire(geom_er4)
        assert r_er4.z_gcz == pytest.approx(r_air.z_gcz / 2.0, rel=1e-9)


class TestRadiationIndicator:
    def test_symmetric_geometry_has_zero_ignd(self) -> None:
        """A geometry with red/blue mirror-symmetric across green has 0 net
        ground current under push-pull drive."""
        spacing = 4e-3
        h = 5e-3
        geom = ThreeWireGeometry(
            a="0.5mm",
            red=WirePosition(x=-spacing / 2, y=h),
            blue=WirePosition(x=spacing / 2, y=h),
            green=WirePosition(x=0, y=h + 5e-3),
            er=1.0,
            ground_plane=True,
        )
        r = solve_three_wire(geom)
        assert r.ignd_ratio == pytest.approx(0.0, abs=1e-6)

    def test_asymmetric_geometry_can_radiate(self) -> None:
        """Strongly asymmetric geometry (red close to ground, blue far) should
        have non-trivial Ignd ratio."""
        geom = ThreeWireGeometry(
            a="0.5mm",
            red=WirePosition(x=0, y=1.5e-3),  # close to ground
            blue=WirePosition(x=4e-3, y=20e-3),  # far from ground
            green=WirePosition(x=2e-3, y=10e-3),
            er=1.0,
            ground_plane=True,
        )
        r = solve_three_wire(geom)
        # Asymmetric → non-zero (don't assert > 4% specifically; just nonzero)
        assert r.ignd_ratio > 0.0


class TestGeometryValidation:
    def test_overlapping_conductors_rejected(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            ThreeWireGeometry(
                a="1mm",
                red=WirePosition(x=0, y=5e-3),
                blue=WirePosition(x=1e-3, y=5e-3),  # only 1mm away, but a=1mm so 2a=2mm
                green=WirePosition(x=0, y=8e-3),
                er=1.0,
            )

    def test_conductor_below_ground_rejected(self) -> None:
        with pytest.raises(ValueError, match="must sit above ground"):
            ThreeWireGeometry(
                a="1mm",
                red=WirePosition(x=0, y=0.5e-3),  # y < a, intersects ground
                blue=WirePosition(x=4e-3, y=5e-3),
                green=WirePosition(x=2e-3, y=8e-3),
                er=1.0,
                ground_plane=True,
            )

    def test_round_trip_via_dict(self) -> None:
        from atlc3.geometry import from_dict

        d = {
            "type": "three_wire",
            "a": "0.5mm",
            "red": {"x": -2e-3, "y": 5e-3},
            "blue": {"x": 2e-3, "y": 5e-3},
            "green": {"x": 0, "y": 8e-3},
            "er": 4.4,
            "ground_plane": True,
        }
        geom = from_dict(d)
        assert isinstance(geom, ThreeWireGeometry)
        assert geom.er == 4.4


class TestDispatcherIntegration:
    def test_dispatcher_routes_three_wire(self) -> None:
        from atlc3.analytical import solve

        geom = ThreeWireGeometry(
            a="0.5mm",
            red=WirePosition(x=-2e-3, y=5e-3),
            blue=WirePosition(x=2e-3, y=5e-3),
            green=WirePosition(x=0, y=8e-3),
            er=1.0,
            ground_plane=True,
        )
        result = solve(geom)
        # Should be a ThreeWireResult, not TLineResult/DiffResult
        from atlc3.results import ThreeWireResult

        assert isinstance(result, ThreeWireResult)
        assert result.method == "closed-form-y-decomposition"
