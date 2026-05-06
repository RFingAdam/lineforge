"""Phase 3.1 AC: skin-depth prediction matches sqrt(2ρ/ωμ); masking reduces equation count."""

from __future__ import annotations

import numpy as np
import pytest

from atlc3.materials.database import MaterialRecord
from atlc3.solvers.skin_depth import compute_delta, mask_skin_depth

COPPER = MaterialRecord(
    rgb=(255, 0, 0),
    use="+1",
    resistivity_ohm_cm=1.7241,
    er=1,
    tan_delta=0,
    mu_r=1,
    name="copper",
)


class TestComputeDelta:
    def test_copper_at_1ghz(self) -> None:
        # Standard textbook value: copper @ 1 GHz, δ ≈ 2.1 µm
        delta = compute_delta(COPPER, 1e9)
        assert delta == pytest.approx(2.1e-6, rel=0.1)

    def test_higher_frequency_smaller_delta(self) -> None:
        d_low = compute_delta(COPPER, 1e6)
        d_high = compute_delta(COPPER, 1e9)
        assert d_high < d_low

    def test_insulator_returns_huge(self) -> None:
        insul = MaterialRecord(
            rgb=(0, 0, 0),
            use="insul",
            resistivity_ohm_cm=1e6,
            er=1.0,
            tan_delta=0,
            mu_r=1,
            name="vacuum",
        )
        assert compute_delta(insul, 1e9) > 1e3


class TestMasking:
    def test_thick_conductor_at_high_f_reduces_equations(self) -> None:
        # 30×30 grid, big red copper square in the middle
        from atlc3.geometry.usermap import Usermap, UsermapMetadata

        rgb = np.full((30, 30, 3), 255, dtype=np.uint8)  # white = vacuum
        rgb[5:25, 5:25] = (255, 0, 0)  # 20×20 copper block
        u = Usermap(rgb, UsermapMetadata(pixel_width_m=1e-6))  # 1 µm pixels

        before = u.conductor_mask("+1").sum()
        masked = mask_skin_depth(u, frequency_hz=10e9, factor=3.0)
        after = masked.conductor_mask("+1").sum()

        # δ at 10 GHz ≈ 0.65 µm, factor*δ ≈ 2 µm = 2 px → mask everything > 2 px from surface
        # 20×20 block with 2-pixel-deep shell ≈ 16×16 interior masked → ~256 fewer pixels
        assert after < before
        assert (before - after) > 100
