"""Phase 1.2 AC: CPWG (coplanar waveguide with ground) tests via Wen elliptic-integral formula."""

from __future__ import annotations

import pytest

from atlc3.analytical.wadell import cpwg
from atlc3.geometry.types import CPWG


class TestCPWG:
    @pytest.mark.parametrize(
        ("W_mil", "S_mil", "H_mil", "T_mil", "er", "z0_expected", "tol"),
        [
            # CPWG closed-form (Wen 1969) is ±15-20% accurate vs empirical
            # fits (Polar SI9000, Saturn). Tight-tolerance work should use
            # the bitmap solver. Expected values below come from the Wen
            # formula published values.
            (5.0, 4.0, 4.0, 1.4, 4.4, 60.0, 0.15),
            (5.0, 8.0, 4.0, 1.4, 4.4, 65.0, 0.15),
            (15.0, 8.0, 4.0, 1.4, 4.4, 32.0, 0.20),
            (5.0, 20.0, 4.0, 1.4, 4.4, 68.0, 0.15),
        ],
    )
    def test_golden(
        self,
        W_mil: float,
        S_mil: float,
        H_mil: float,
        T_mil: float,
        er: float,
        z0_expected: float,
        tol: float,
    ) -> None:
        geom = CPWG(
            W=W_mil * 25.4e-6,
            S=S_mil * 25.4e-6,
            H=H_mil * 25.4e-6,
            T=T_mil * 25.4e-6,
            er=er,
        )
        result = cpwg(geom)
        assert result.z0 == pytest.approx(z0_expected, rel=tol)

    def test_eps_eff_below_er(self) -> None:
        """For air-above CPWG, εeff < εr always."""
        result = cpwg(CPWG(W="5mil", S="8mil", H="4mil", T="1.4mil", er=4.4))
        assert 1.0 < result.eps_eff < 4.4

    def test_increasing_w_decreases_z0(self) -> None:
        narrow = cpwg(CPWG(W="3mil", S="8mil", H="4mil", T="1.4mil", er=4.4))
        wide = cpwg(CPWG(W="20mil", S="8mil", H="4mil", T="1.4mil", er=4.4))
        assert wide.z0 < narrow.z0

    def test_increasing_gap_increases_z0(self) -> None:
        small = cpwg(CPWG(W="5mil", S="3mil", H="4mil", T="1.4mil", er=4.4))
        big = cpwg(CPWG(W="5mil", S="20mil", H="4mil", T="1.4mil", er=4.4))
        assert big.z0 > small.z0
