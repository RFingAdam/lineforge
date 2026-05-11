"""Phase 1.3 AC: differential pair golden tests."""

from __future__ import annotations

import pytest

from lineforge.analytical.wadell import (
    broadside_coupled_diff_stripline,
    edge_coupled_diff_microstrip,
    edge_coupled_diff_stripline,
)
from lineforge.geometry.types import (
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
)


class TestEdgeCoupledMicrostrip:
    def test_classic_100ohm_diff(self) -> None:
        # Common 100Ω diff microstrip target on 4 mil FR4
        result = edge_coupled_diff_microstrip(
            EdgeCoupledDiffMicrostrip(
                W="4mil",
                S="6mil",
                H="4mil",
                T="1.4mil",
                er=4.4,
            )
        )
        assert result.z_diff == pytest.approx(100.0, rel=0.15)

    def test_zdiff_equals_2_zodd(self) -> None:
        result = edge_coupled_diff_microstrip(
            EdgeCoupledDiffMicrostrip(W="4mil", S="6mil", H="4mil", T="1.4mil", er=4.4)
        )
        assert result.z_diff == pytest.approx(2 * result.z_odd)

    def test_zcommon_equals_zeven_over_2(self) -> None:
        result = edge_coupled_diff_microstrip(
            EdgeCoupledDiffMicrostrip(W="4mil", S="6mil", H="4mil", T="1.4mil", er=4.4)
        )
        assert result.z_common == pytest.approx(result.z_even / 2)

    def test_wider_gap_increases_zdiff(self) -> None:
        tight = edge_coupled_diff_microstrip(
            EdgeCoupledDiffMicrostrip(W="4mil", S="3mil", H="4mil", T="1.4mil", er=4.4)
        )
        loose = edge_coupled_diff_microstrip(
            EdgeCoupledDiffMicrostrip(W="4mil", S="15mil", H="4mil", T="1.4mil", er=4.4)
        )
        assert loose.z_diff > tight.z_diff


class TestEdgeCoupledStripline:
    def test_classic_100ohm_diff(self) -> None:
        result = edge_coupled_diff_stripline(
            EdgeCoupledDiffStripline(W="4mil", S="6mil", B="14mil", T="1.4mil", er=4.4)
        )
        assert 70 < result.z_diff < 130, f"got Zdiff={result.z_diff}"

    def test_zdiff_equals_2_zodd(self) -> None:
        result = edge_coupled_diff_stripline(
            EdgeCoupledDiffStripline(W="4mil", S="6mil", B="14mil", T="1.4mil", er=4.4)
        )
        assert result.z_diff == pytest.approx(2 * result.z_odd)


class TestBroadsideCoupledStripline:
    def test_basic_solve(self) -> None:
        result = broadside_coupled_diff_stripline(
            BroadsideCoupledDiffStripline(
                W="5mil",
                H1="4mil",
                H_between="4mil",
                T="0.7mil",
                er=4.4,
            )
        )
        assert result.z_odd > 0
        assert result.z_even > result.z_odd
        assert result.z_diff == pytest.approx(2 * result.z_odd)

    def test_increasing_h_between_changes_modes(self) -> None:
        tight = broadside_coupled_diff_stripline(
            BroadsideCoupledDiffStripline(
                W="5mil",
                H1="4mil",
                H_between="2mil",
                T="0.7mil",
                er=4.4,
            )
        )
        loose = broadside_coupled_diff_stripline(
            BroadsideCoupledDiffStripline(
                W="5mil",
                H1="4mil",
                H_between="10mil",
                T="0.7mil",
                er=4.4,
            )
        )
        # Tighter coupling lowers Z_odd (more coupling)
        assert tight.z_odd < loose.z_odd
