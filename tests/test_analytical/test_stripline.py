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
        self,
        W_mil: float,
        T_mil: float,
        B_mil: float,
        er: float,
        z0_expected: float,
        tol: float,
    ) -> None:
        geom = StriplineSymmetric(
            W=W_mil * 25.4e-6,
            T=T_mil * 25.4e-6,
            B=B_mil * 25.4e-6,
            er=er,
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
        thin = stripline_symmetric(StriplineSymmetric(W="5mil", T="0.7mil", B="14mil", er=4.4))
        thick = stripline_symmetric(StriplineSymmetric(W="5mil", T="2.8mil", B="14mil", er=4.4))
        assert thick.z0 < thin.z0

    def test_z0_squared_equals_l_over_c(self) -> None:
        result = stripline_symmetric(StriplineSymmetric(W="5mil", T="1.4mil", B="14mil", er=4.4))
        assert result.L_per_m is not None
        assert result.C_per_m is not None
        z0_from_lc = (result.L_per_m / result.C_per_m) ** 0.5
        assert z0_from_lc == pytest.approx(result.z0, rel=1e-6)


class TestStriplineAsymmetric:
    """Asymmetric stripline reduces to symmetric when H1 == H2."""

    def test_symmetric_limit(self) -> None:
        sym = stripline_symmetric(StriplineSymmetric(W="5mil", T="1.4mil", B="14mil", er=4.4))
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


class TestStriplineAsymmetricSplitEr:
    """Split-εr (Core above ≠ Prepreg below) — capacitance-weighted εr_eff."""

    def test_split_er_collapses_to_bulk_when_equal(self) -> None:
        """er_above == er_below == er must reproduce the bulk-only result exactly."""
        bulk = stripline_asymmetric(
            StriplineAsymmetric(W="5mil", T="1.4mil", H1="3mil", H2="9mil", er=4.4)
        )
        split = stripline_asymmetric(
            StriplineAsymmetric(
                W="5mil",
                T="1.4mil",
                H1="3mil",
                H2="9mil",
                er=4.4,
                er_above=4.4,
                er_below=4.4,
            )
        )
        assert split.z0 == pytest.approx(bulk.z0, rel=1e-12)
        assert split.eps_eff == pytest.approx(bulk.eps_eff, rel=1e-12)

    def test_split_er_method_tag_flips(self) -> None:
        bulk = stripline_asymmetric(
            StriplineAsymmetric(W="5mil", T="1.4mil", H1="3mil", H2="9mil", er=4.4)
        )
        split = stripline_asymmetric(
            StriplineAsymmetric(
                W="5mil", T="1.4mil", H1="3mil", H2="9mil", er=4.4, er_above=4.5, er_below=3.7
            )
        )
        assert bulk.method == "ipc2141-stripline-asymmetric"
        assert split.method == "ipc2141-stripline-asymmetric-split-er"

    def test_eps_eff_capacitance_weighted(self) -> None:
        """εr_eff = (εr_above/H1 + εr_below/H2) / (1/H1 + 1/H2)."""
        H1_mil, H2_mil = 8.0, 4.0
        er_above, er_below = 4.2, 3.7
        result = stripline_asymmetric(
            StriplineAsymmetric(
                W="5mil",
                T="1.4mil",
                H1=f"{H1_mil}mil",
                H2=f"{H2_mil}mil",
                er=4.0,  # ignored when split er_above/er_below are present
                er_above=er_above,
                er_below=er_below,
            )
        )
        expected_eps_eff = (er_above / H1_mil + er_below / H2_mil) / (1.0 / H1_mil + 1.0 / H2_mil)
        assert result.eps_eff == pytest.approx(expected_eps_eff, rel=1e-9)
        # The closer (smaller-H) dielectric must dominate.
        assert result.eps_eff < (er_above + er_below) / 2  # H2 < H1 → er_below pulls harder

    def test_loss_tangent_capacitance_weighted(self) -> None:
        """tan_delta_eff weights by the same C contributions as εr_eff."""
        H1_mil, H2_mil = 8.0, 4.0
        er_above, er_below = 4.2, 3.7
        td_above, td_below = 0.020, 0.005
        result = stripline_asymmetric(
            StriplineAsymmetric(
                W="5mil",
                T="1.4mil",
                H1=f"{H1_mil}mil",
                H2=f"{H2_mil}mil",
                er=4.0,
                tan_delta=0.01,
                er_above=er_above,
                er_below=er_below,
                tan_delta_above=td_above,
                tan_delta_below=td_below,
            ),
            frequency_hz=1e9,
        )
        # The closer (smaller H2) dielectric (low-loss prepreg) should pull
        # tan_delta_eff toward td_below.
        unweighted_avg = (td_above + td_below) / 2
        assert result.dielectric_loss_db_per_in is not None
        # Compare against a bulk-only run with the unweighted average:
        ref = stripline_asymmetric(
            StriplineAsymmetric(
                W="5mil",
                T="1.4mil",
                H1=f"{H1_mil}mil",
                H2=f"{H2_mil}mil",
                er=result.eps_eff,
                tan_delta=unweighted_avg,
            ),
            frequency_hz=1e9,
        )
        assert ref.dielectric_loss_db_per_in is not None
        # split run should have LOWER loss than the unweighted-avg run, because
        # the high-loss core (td_above) gets weighted DOWN by 1/H1 (larger H).
        assert result.dielectric_loss_db_per_in < ref.dielectric_loss_db_per_in
