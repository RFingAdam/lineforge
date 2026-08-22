"""Tests for multi-layer dielectric stack support on StriplineAsymmetric.

The stack collapses to a single equivalent εr/tan_δ via the parallel-plate
(C-series) reduction; that equivalent then plugs into the existing split-εr
code path. So we test:

1. ``series_reduce`` math against hand-computed values.
2. The Pydantic validator derives H1/H2/εr_above/εr_below from stacks correctly.
3. Equivalence: a stack of identical layers produces the same Z₀ as a single
   layer with their summed thickness.
4. The L3 SIG1 void-L4 stackup from the planning session reproduces
   Z₀ ≈ 52.06 Ω, εr_eff ≈ 4.11.
5. Method tag flips to ``ipc2141-stripline-asymmetric-multilayer-stack`` when
   stacks are used.
6. Validator rejects ambiguous input (stack + explicit H/εr for the same side).
"""

from __future__ import annotations

import pytest

from lineforge.analytical.wadell import stripline_asymmetric
from lineforge.geometry.dielectric import DielectricLayer, series_reduce
from lineforge.geometry.types import StriplineAsymmetric


class TestSeriesReduce:
    def test_single_layer_passthrough(self) -> None:
        layer = DielectricLayer(h="3mil", er=4.2, tan_delta=0.01)
        h, er, tan = series_reduce([layer])
        assert h == pytest.approx(3 * 25.4e-6)
        assert er == pytest.approx(4.2)
        assert tan == pytest.approx(0.01)

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one layer"):
            series_reduce([])

    def test_void_l4_stackup(self) -> None:
        """The exact L3 SIG1 void-L4 case: 5.3 mil Prepreg + 1.4 mil voided +
        3.5 mil Core. Expected εr_eq = 3.858 (matches hand calculation in the
        planning session)."""
        layers = [
            DielectricLayer(h="5.3mil", er=3.7, tan_delta=0.020),
            DielectricLayer(h="1.4mil", er=3.7, tan_delta=0.020),
            DielectricLayer(h="3.5mil", er=4.2, tan_delta=0.020),
        ]
        h_total, er_eq, tan_eq = series_reduce(layers)
        assert h_total == pytest.approx(10.2 * 25.4e-6)
        assert er_eq == pytest.approx(3.858, abs=1e-3)
        assert tan_eq == pytest.approx(0.020, abs=1e-6)  # all same → unchanged

    def test_loss_tangent_weighted(self) -> None:
        """When layers have different tan_δ, the weighting is by h/εr (series
        conductance contribution)."""
        layers = [
            DielectricLayer(h="3mil", er=4.0, tan_delta=0.020),  # weight 3/4 = 0.75
            DielectricLayer(h="6mil", er=4.0, tan_delta=0.005),  # weight 6/4 = 1.5
        ]
        _, _, tan_eq = series_reduce(layers)
        expected = (0.020 * 0.75 + 0.005 * 1.5) / (0.75 + 1.5)
        assert tan_eq == pytest.approx(expected, rel=1e-9)

    def test_order_independence(self) -> None:
        """Series-cap reduction is order-independent."""
        a = DielectricLayer(h="3mil", er=4.2)
        b = DielectricLayer(h="5mil", er=3.5)
        c = DielectricLayer(h="2mil", er=10.0)
        forward = series_reduce([a, b, c])
        reverse = series_reduce([c, b, a])
        for f, r in zip(forward, reverse, strict=True):
            assert f == pytest.approx(r, rel=1e-12)


class TestStriplineAsymmetricStackValidation:
    def test_stack_below_derives_h2_er_below_tan_below(self) -> None:
        geom = StriplineAsymmetric(
            W="3.4mil",
            T="0.689mil",
            H1="3.5mil",
            er=4.2,
            er_above=4.2,
            tan_delta_above=0.020,
            stack_below=[
                {"h": "5.3mil", "er": 3.7, "tan_delta": 0.020},
                {"h": "1.4mil", "er": 3.7, "tan_delta": 0.020},
                {"h": "3.5mil", "er": 4.2, "tan_delta": 0.020},
            ],
        )
        assert geom.H2 == pytest.approx(10.2 * 25.4e-6)
        assert geom.er_below == pytest.approx(3.858, abs=1e-3)
        assert geom.tan_delta_below == pytest.approx(0.020, abs=1e-6)
        # Materialized as DielectricLayer instances:
        assert geom.stack_below is not None
        assert all(isinstance(layer, DielectricLayer) for layer in geom.stack_below)

    def test_two_sided_stacks(self) -> None:
        geom = StriplineAsymmetric(
            W="3.4mil",
            T="0.689mil",
            stack_above=[{"h": "3.5mil", "er": 4.2, "tan_delta": 0.020}],
            stack_below=[
                {"h": "5.3mil", "er": 3.7, "tan_delta": 0.020},
                {"h": "3.5mil", "er": 4.2, "tan_delta": 0.020},
            ],
        )
        assert geom.H1 == pytest.approx(3.5 * 25.4e-6)
        assert geom.H2 == pytest.approx(8.8 * 25.4e-6)
        assert geom.er_above == pytest.approx(4.2)
        # stack_below εr_eq via formula
        expected_er_below = 8.8 / (5.3 / 3.7 + 3.5 / 4.2)
        assert geom.er_below == pytest.approx(expected_er_below, abs=1e-3)

    def test_rejects_ambiguous_h2_with_stack(self) -> None:
        with pytest.raises(ValueError, match="cannot pass both stack_below and H2"):
            StriplineAsymmetric(
                W="3.4mil",
                T="0.689mil",
                H1="3.5mil",
                H2="10mil",  # ambiguous with stack_below
                er=4.0,
                stack_below=[{"h": "5.3mil", "er": 3.7}],
            )

    def test_rejects_inconsistent_er_above_with_stack(self) -> None:
        """A stack and an explicit er_above that disagrees must error.
        (Consistent redundancy: same value: is allowed for JSON round-tripping.)"""
        with pytest.raises(ValueError, match="cannot pass both stack_above and er_above"):
            StriplineAsymmetric(
                W="3.4mil",
                T="0.689mil",
                H2="5.3mil",
                er=4.0,
                er_above=3.5,  # disagrees with stack-derived 4.2
                stack_above=[{"h": "3.5mil", "er": 4.2}],
            )

    def test_round_trip_json(self) -> None:
        """Stacks survive a JSON round-trip."""
        original = StriplineAsymmetric(
            W="3.4mil",
            T="0.689mil",
            H1="3.5mil",
            er=4.2,
            er_above=4.2,
            stack_below=[
                {"h": "5.3mil", "er": 3.7, "tan_delta": 0.020, "name": "Prepreg"},
                {"h": "3.5mil", "er": 4.2, "tan_delta": 0.020, "name": "Core"},
            ],
        )
        s = original.model_dump_json()
        restored = StriplineAsymmetric.model_validate_json(s)
        assert restored.H2 == pytest.approx(original.H2)
        assert restored.er_below == pytest.approx(original.er_below)
        assert restored.stack_below is not None
        assert restored.stack_below[0].name == "Prepreg"


class TestStriplineAsymmetricStackSolve:
    def test_void_l4_l3_sig1_z0(self) -> None:
        """L3 SIG1 with L4 voided: prep+voided+core below = 10.2 mil eq.

        Hand calculation from the planning session: Z₀ ≈ 52.06 Ω,
        εr_eff ≈ 4.11. This test locks that result in.
        """
        geom = StriplineAsymmetric(
            W="3.4mil",
            T="0.689mil",
            H1="3.5mil",
            er=4.2,
            er_above=4.2,
            tan_delta_above=0.020,
            stack_below=[
                {"h": "5.3mil", "er": 3.7, "tan_delta": 0.020, "name": "Prepreg"},
                {"h": "1.4mil", "er": 3.7, "tan_delta": 0.020, "name": "L4 voided"},
                {"h": "3.5mil", "er": 4.2, "tan_delta": 0.020, "name": "Core"},
            ],
        )
        result = stripline_asymmetric(geom, frequency_hz=1e9)
        assert result.z0 == pytest.approx(52.06, abs=0.05)
        assert result.eps_eff == pytest.approx(4.113, abs=1e-3)
        assert result.method == "ipc2141-stripline-asymmetric-multilayer-stack"
        assert result.dielectric_loss_db_per_in is not None
        assert result.dielectric_loss_db_per_in > 0

    def test_method_tag_when_stack_present(self) -> None:
        bulk = stripline_asymmetric(
            StriplineAsymmetric(W="3.4mil", T="0.689mil", H1="3.5mil", H2="5.3mil", er=4.0)
        )
        with_stack = stripline_asymmetric(
            StriplineAsymmetric(
                W="3.4mil",
                T="0.689mil",
                H1="3.5mil",
                er=4.0,
                er_above=4.2,
                stack_below=[
                    {"h": "5.3mil", "er": 3.7},
                    {"h": "3.5mil", "er": 4.2},
                ],
            )
        )
        assert bulk.method == "ipc2141-stripline-asymmetric"
        assert with_stack.method == "ipc2141-stripline-asymmetric-multilayer-stack"

    def test_stack_of_identical_layers_matches_single_layer(self) -> None:
        """Three identical Core layers (each 2 mil, εr=4.2) summed to 6 mil
        single layer must give the same Z₀ as a single 6 mil layer with εr=4.2.
        """
        single = stripline_asymmetric(
            StriplineAsymmetric(
                W="3.4mil",
                T="0.689mil",
                H1="3.5mil",
                H2="6mil",
                er=4.2,
                er_above=4.2,
                er_below=4.2,
            )
        )
        stacked = stripline_asymmetric(
            StriplineAsymmetric(
                W="3.4mil",
                T="0.689mil",
                H1="3.5mil",
                er=4.2,
                er_above=4.2,
                stack_below=[
                    {"h": "2mil", "er": 4.2},
                    {"h": "2mil", "er": 4.2},
                    {"h": "2mil", "er": 4.2},
                ],
            )
        )
        assert stacked.z0 == pytest.approx(single.z0, rel=1e-9)
        assert stacked.eps_eff == pytest.approx(single.eps_eff, rel=1e-9)

    def test_stack_collapse_to_split_er(self) -> None:
        """A single-layer stack on each side must give the same Z₀ as the
        equivalent ``er_above``/``er_below`` call (no stack)."""
        with_split = stripline_asymmetric(
            StriplineAsymmetric(
                W="3.4mil",
                T="0.689mil",
                H1="3.5mil",
                H2="5.3mil",
                er=4.0,
                er_above=4.2,
                er_below=3.7,
            )
        )
        with_stacks = stripline_asymmetric(
            StriplineAsymmetric(
                W="3.4mil",
                T="0.689mil",
                stack_above=[{"h": "3.5mil", "er": 4.2}],
                stack_below=[{"h": "5.3mil", "er": 3.7}],
            )
        )
        assert with_stacks.z0 == pytest.approx(with_split.z0, rel=1e-9)
        assert with_stacks.eps_eff == pytest.approx(with_split.eps_eff, rel=1e-9)


class TestStriplineAsymmetricStackRasterize:
    def test_rasterizer_paints_each_layer_distinctly(self) -> None:
        """Multi-layer stack_below produces N distinct dielectric colors in the
        bitmap so the solver and the human can see the stratification."""
        from lineforge.geometry.builders import rasterize_stripline_asymmetric

        geom = StriplineAsymmetric(
            W="3.4mil",
            T="0.689mil",
            H1="3.5mil",
            er=4.2,
            er_above=4.2,
            stack_below=[
                {"h": "5.3mil", "er": 3.7, "name": "Prepreg"},
                {"h": "1.4mil", "er": 3.7, "name": "L4 voided"},  # same εr but separate
                {"h": "3.5mil", "er": 4.2, "name": "Core"},
            ],
        )
        umap = rasterize_stripline_asymmetric(geom)
        # Sample a column away from the strip
        col = umap.rgb[:, 1, :]
        unique = {tuple(row) for row in col}
        unique.discard((0, 255, 0))  # ground
        unique.discard((255, 255, 255))  # vacuum margin
        # Expect: 1 above color + 3 below colors = 4 distinct dielectric colors.
        assert len(unique) >= 4, f"expected ≥4 distinct dielectric colors, got {unique}"

    def test_rasterizer_lookup_carries_layer_names(self) -> None:
        from lineforge.geometry.builders import rasterize_stripline_asymmetric

        geom = StriplineAsymmetric(
            W="3.4mil",
            T="0.689mil",
            H1="3.5mil",
            er=4.2,
            er_above=4.2,
            stack_below=[
                {"h": "5.3mil", "er": 3.7, "tan_delta": 0.020, "name": "Megtron Prepreg"},
                {"h": "3.5mil", "er": 4.2, "tan_delta": 0.020, "name": "Megtron Core"},
            ],
        )
        umap = rasterize_stripline_asymmetric(geom)
        names = {rec.name for rec in umap.material_lookup.values() if rec.use == "insul"}
        assert any("Megtron Prepreg" in n for n in names if n)
        assert any("Megtron Core" in n for n in names if n)
