"""Phase 1.2 AC: Stripline (symmetric + asymmetric) golden tests."""

from __future__ import annotations

import pytest

from atlc3.analytical.wadell import stripline_asymmetric, stripline_symmetric
from atlc3.geometry.types import StriplineAsymmetric, StriplineSymmetric


class TestStriplineSymmetric:
    """Reference values from common 50Ω PCB stripline stackups."""

    @pytest.mark.parametrize(
        ("W_mil", "T_mil", "B_mil", "er", "z0_expected", "tol"),
        [
            # 50Ω stripline on FR4 (er=4.4), 5 mil trace between 8 mil plates
            (5.0, 1.4, 14.0, 4.4, 50.0, 0.10),
            # Wider trace, lower Z0
            (10.0, 1.4, 14.0, 4.4, 30.0, 0.15),
            # Higher εr (Rogers RO3010 er≈10.2), narrower trace for 50Ω
            (4.0, 1.4, 14.0, 10.2, 35.0, 0.15),
        ],
    )
    def test_golden(
        self, W_mil: float, T_mil: float, B_mil: float, er: float,
        z0_expected: float, tol: float,
    ) -> None:
        geom = StriplineSymmetric(
            W=W_mil * 25.4e-6, T=T_mil * 25.4e-6, B=B_mil * 25.4e-6, er=er,
        )
        result = stripline_symmetric(geom)
        assert result.z0 == pytest.approx(z0_expected, rel=tol), (
            f"W={W_mil}mil B={B_mil}mil er={er}: got Z0={result.z0:.2f}Ω, "
            f"expected ~{z0_expected:.2f}Ω"
        )

    def test_eps_eff_equals_er(self) -> None:
        """Stripline is fully embedded — εeff should equal εr exactly."""
        geom = StriplineSymmetric(W="5mil", T="1.4mil", B="14mil", er=4.4)
        result = stripline_symmetric(geom)
        assert result.eps_eff == pytest.approx(4.4, rel=1e-9)

    def test_thicker_strip_lowers_z0(self) -> None:
        thin = stripline_symmetric(
            StriplineSymmetric(W="5mil", T="0.7mil", B="14mil", er=4.4)
        )
        thick = stripline_symmetric(
            StriplineSymmetric(W="5mil", T="2.8mil", B="14mil", er=4.4)
        )
        assert thick.z0 < thin.z0

    def test_z0_squared_equals_l_over_c(self) -> None:
        result = stripline_symmetric(
            StriplineSymmetric(W="5mil", T="1.4mil", B="14mil", er=4.4)
        )
        assert result.L_per_m is not None
        assert result.C_per_m is not None
        z0_from_lc = (result.L_per_m / result.C_per_m) ** 0.5
        assert z0_from_lc == pytest.approx(result.z0, rel=1e-6)


class TestStriplineAsymmetric:
    """Asymmetric stripline reduces to symmetric when H1 == H2."""

    def test_symmetric_limit(self) -> None:
        sym = stripline_symmetric(
            StriplineSymmetric(W="5mil", T="1.4mil", B="14mil", er=4.4)
        )
        # H1 = H2 = (B - T) / 2 reproduces the symmetric case
        H_each_m = (14.0 - 1.4) / 2 * 25.4e-6
        T_m = 1.4 * 25.4e-6
        asym = stripline_asymmetric(
            StriplineAsymmetric(W=5 * 25.4e-6, T=T_m, H1=H_each_m, H2=H_each_m, er=4.4)
        )
        # The two-stripline-in-parallel approximation gives slightly lower Z0;
        # accept ±15% deviation in this Phase 1 model.
        assert asym.z0 == pytest.approx(sym.z0, rel=0.15)

    def test_offset_changes_z0(self) -> None:
        centered = stripline_asymmetric(
            StriplineAsymmetric(W="5mil", T="1.4mil", H1="6mil", H2="6mil", er=4.4)
        )
        offset = stripline_asymmetric(
            StriplineAsymmetric(W="5mil", T="1.4mil", H1="2mil", H2="10mil", er=4.4)
        )
        # Offsetting changes the impedance noticeably.
        assert abs(offset.z0 - centered.z0) / centered.z0 > 0.05
