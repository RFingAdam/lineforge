"""Tests for lineforge.path_budget."""
from __future__ import annotations

from lineforge.analytical.pads import pad_capacitance
from lineforge.path_budget import TraceSpec, rf_path_budget


class TestRfPathBudget:
    def test_pad_only_no_trace(self):
        """No trace, just two pads — RL is sum of two shunt contributions."""
        src = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7)
        end = pad_capacitance("0.6mm", "0.5mm", h="2.73mil", er=3.7)
        b = rf_path_budget(freq_ghz=[1.0, 6.0], source_pad=src, end_pad=end)
        assert len(b.rows) == 2
        # 6 GHz should be worse than 1 GHz
        assert b.rows[1].combined_rl_dB < b.rows[0].combined_rl_dB

    def test_trace_only_constant_RL(self):
        """Trace mismatch is frequency-independent."""
        trace = TraceSpec(Z0=56.0)
        b = rf_path_budget(freq_ghz=[0.5, 2.0, 6.0], trace=trace)
        rl_values = [r.combined_rl_dB for r in b.rows]
        # All should be equal
        assert all(abs(r - rl_values[0]) < 0.1 for r in rl_values)

    def test_combined_rl_worse_than_individual(self):
        """Combined (in-phase sum) is worse than any single contributor."""
        src = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7)
        end = pad_capacitance("0.6mm", "0.5mm", h="2.73mil", er=3.7)
        trace = TraceSpec(Z0=56.0)
        b = rf_path_budget(freq_ghz=[6.0], source_pad=src, trace=trace, end_pad=end)
        row = b.rows[0]
        # Each individual contribution is some negative dB; combined is more
        # negative (= worse RL = lower combined_rl_dB number)
        worst_individual = min(
            row.s11_source_dB, row.s11_trace_dB, row.s11_end_dB,
        )
        # combined_rl_dB = -s11_combined_dB; should be ≤ worst |individual|
        assert row.combined_rl_dB <= -worst_individual

    def test_dominant_contributor(self):
        """dominant property identifies the worst element."""
        # Use a huge trace mismatch so it dominates
        trace = TraceSpec(Z0=75.0)
        src = pad_capacitance("0.2mm", "0.2mm", h="8mil", er=3.7)
        b = rf_path_budget(freq_ghz=[1.0], source_pad=src, trace=trace)
        assert b.rows[0].dominant == "trace"

    def test_worst_rl_finds_minimum(self):
        src = pad_capacitance("0.4mm", "0.4mm", h="2.73mil", er=3.7)
        end = pad_capacitance("0.6mm", "0.5mm", h="2.73mil", er=3.7)
        b = rf_path_budget(freq_ghz=[1.0, 3.0, 6.0], source_pad=src, end_pad=end)
        worst = b.worst_rl_dB
        assert worst == min(r.combined_rl_dB for r in b.rows)

    def test_empty_budget(self):
        """No pads or trace → infinite RL."""
        b = rf_path_budget(freq_ghz=[1.0, 6.0])
        for row in b.rows:
            assert row.combined_rl_dB == float("inf")
