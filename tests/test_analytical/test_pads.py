"""Tests for lineforge.analytical.pads."""
from __future__ import annotations

import pytest

from lineforge.analytical.pads import (
    ReliefOption,
    pad_capacitance,
    pad_relief_advisor,
)
from lineforge.geometry.dielectric import DielectricLayer


class TestPadCapacitance:
    """pad_capacitance — three methods, multiple geometries."""

    def test_parallel_plate_basic(self):
        """0.4mm × 0.4mm pad over 2.73 mil prepreg εr=3.7 → ~76 fF."""
        r = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7, method="pp")
        assert r.method == "pp"
        assert r.fringing_factor == 1.0
        # Expected from session analysis: 75.6 fF
        assert 73 < r.C_fF < 78

    def test_yamashita_atsuki_adds_fringing(self):
        """YA method gives larger cap than PP due to fringing."""
        r_pp = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7, method="pp")
        r_ya = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7, method="ya")
        assert r_ya.C_fF > r_pp.C_fF
        assert r_ya.fringing_factor > 1.0
        # Session analysis target: ~105 fF
        assert 100 < r_ya.C_fF < 110

    def test_hammerstad_jensen_method(self):
        """HJ method also includes fringing, lands between PP and YA for
        small h/W; closer to YA for larger h/W."""
        r_pp = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7, method="pp")
        r_hj = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7, method="hj")
        assert r_hj.C_fF > r_pp.C_fF

    def test_square_pad_default_L(self):
        """L defaults to W for square pads."""
        r_explicit = pad_capacitance("0.3mm", "0.3mm", h="2.73mil", er=3.7)
        r_default = pad_capacitance("0.3mm", h="2.73mil", er=3.7)
        assert r_explicit.C_fF == pytest.approx(r_default.C_fF)

    def test_rectangular_pad(self):
        """U.FL-shape rectangular pad (0.6 × 0.5 mm)."""
        r = pad_capacitance("0.6mm", "0.5mm", h="2.73mil", er=3.7)
        # Larger area than 0.4×0.4 → larger cap
        r_smaller = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7)
        assert r.C_fF > r_smaller.C_fF

    def test_stack_input_matches_single_layer(self):
        """Stack with one layer matches single (h, er) input."""
        single = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7)
        stack = pad_capacitance(
            "0.4mm", "0.4mm",
            stack=[DielectricLayer(h="2.73mil", er=3.7)],
        )
        assert single.C_F == pytest.approx(stack.C_F)

    def test_stack_multi_layer_series_reduce(self):
        """Three-layer stack matches the analytical series reduction."""
        r = pad_capacitance(
            "0.4mm", "0.4mm",
            stack=[
                DielectricLayer(h="2.73mil", er=3.7),
                DielectricLayer(h="1.4mil",  er=3.7),
                DielectricLayer(h="3.5mil",  er=4.2),
            ],
        )
        # Session expected: ~49 fF
        assert 45 < r.C_fF < 55

    def test_impedance_at_frequency(self):
        """Z_pad = 1/(jωC) computed correctly."""
        r = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7)
        Z = r.impedance(6e9)
        # Pure capacitor → negative imaginary impedance
        assert Z.real == pytest.approx(0)
        assert Z.imag < 0
        # |Z| at 6 GHz for ~105 fF should be ~253 Ω
        assert 240 < abs(Z) < 270

    def test_return_loss_dB(self):
        """RL @ 6 GHz matches the session value (~20 dB for solid L2)."""
        r = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7)
        rl = r.return_loss_dB(6e9)
        # Session expected: 20.2 dB
        assert 19 < rl < 22

    def test_invalid_method(self):
        with pytest.raises(ValueError, match="Unknown method"):
            pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7, method="invalid")  # type: ignore[arg-type]

    def test_invalid_dimensions(self):
        with pytest.raises(ValueError, match="must be positive"):
            pad_capacitance(0, 0.001, h="2.73mil", er=3.7)

    def test_cannot_provide_both_h_er_and_stack(self):
        with pytest.raises(ValueError, match=r"either .* OR stack"):
            pad_capacitance(
                "0.4mm", "0.4mm", h="2.73mil", er=3.7,
                stack=[DielectricLayer(h="2.73mil", er=3.7)],
            )

    def test_empty_stack_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            pad_capacitance("0.4mm", "0.4mm", stack=[])


class TestPadReliefAdvisor:
    """pad_relief_advisor — ranks options against an RL target."""

    @pytest.fixture
    def triplexer_options(self) -> list[ReliefOption]:
        """The 0.4 mm triplexer pad options from the case study."""
        return [
            ReliefOption(
                name="A: solid L2",
                stack=[DielectricLayer(h="2.73mil", er=3.7)],
            ),
            ReliefOption(
                name="B: relieve L2 → L3",
                stack=[
                    DielectricLayer(h="2.73mil", er=3.7),
                    DielectricLayer(h="1.4mil",  er=3.7),
                    DielectricLayer(h="3.5mil",  er=4.2),
                ],
            ),
            ReliefOption(
                name="C: relieve L2+L3 → L4",
                stack=[
                    DielectricLayer(h="2.73mil",  er=3.7),
                    DielectricLayer(h="1.4mil",   er=3.7),
                    DielectricLayer(h="3.5mil",   er=4.2),
                    DielectricLayer(h="0.689mil", er=3.7),
                    DielectricLayer(h="5.3mil",   er=3.7),
                ],
            ),
        ]

    def test_recommends_option_C_for_strict_RL(self, triplexer_options):
        """At 6 GHz with 30 dB target, only Option C qualifies."""
        advice = pad_relief_advisor(
            "0.4mm", "0.4mm",
            options=triplexer_options,
            band_max_ghz=6.0,
            rl_target_dB=30.0,
        )
        assert advice.recommendation == "C: relieve L2+L3 → L4"

    def test_recommends_option_A_when_target_easy(self, triplexer_options):
        """At 1 GHz with 30 dB target, even Option A qualifies."""
        advice = pad_relief_advisor(
            "0.4mm", "0.4mm",
            options=triplexer_options,
            band_max_ghz=1.0,
            rl_target_dB=30.0,
        )
        # First option that qualifies, in order
        assert advice.recommendation == "A: solid L2"

    def test_no_recommendation_when_unmeetable(self, triplexer_options):
        """At 6 GHz with 50 dB target, nothing qualifies."""
        advice = pad_relief_advisor(
            "0.4mm", "0.4mm",
            options=triplexer_options,
            band_max_ghz=6.0,
            rl_target_dB=50.0,
        )
        assert advice.recommendation is None

    def test_rows_have_capacitance_and_RL(self, triplexer_options):
        advice = pad_relief_advisor(
            "0.4mm", "0.4mm",
            options=triplexer_options,
            band_max_ghz=6.0,
        )
        assert len(advice.rows) == 3
        for row in advice.rows:
            assert row.C.C_F > 0
            assert row.Z_at_band_max > 0
            assert row.RL_at_band_max > 0
            assert isinstance(row.meets_target, bool)

    def test_RL_decreases_with_more_capacitance(self, triplexer_options):
        """More capacitance (Option A) → worse RL than less (Option C)."""
        advice = pad_relief_advisor(
            "0.4mm", "0.4mm",
            options=triplexer_options,
            band_max_ghz=6.0,
        )
        rows_by_name = {r.name: r for r in advice.rows}
        assert (
            rows_by_name["A: solid L2"].RL_at_band_max
            < rows_by_name["B: relieve L2 → L3"].RL_at_band_max
            < rows_by_name["C: relieve L2+L3 → L4"].RL_at_band_max
        )
