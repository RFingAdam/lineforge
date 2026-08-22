"""Phase 3 AC Rs parity: Faraday/PEEC solver vs analytical skin-effect formula for a round-wire pair.

Companion to ``test_coax_ac_rs.py`` (Workstream C-#9). Two parallel solid
round wires of radius ``a``, centre-to-centre spacing ``D``, carrying equal
and opposite currents form a differential loop. In the strong-skin limit
(``a ≫ δ``) the surface-current formula gives a per-wire AC Rs of

    R_per_wire = 1 / (σ · δ · 2π·a)   [Ω/m]

and the loop resistance is twice that (the two wires are in series for the
return path):

    R_loop = 2 / (σ · δ · 2π·a)        [Ω/m]

References
----------
* Pozar, *Microwave Engineering* 4th ed., §2.4: surface impedance of a
  good conductor.
* Wadell, *Transmission Line Design Handbook*, §3.3: round-wire pair.

Test budget
-----------
Same dense-solve constraints as the coax test. We use:

* **Fast** (no marker): a/δ = 3, D = 4·a, δ/px = 3: ~500 conductor pixels,
  ~1 s solve. Asserts ±20%.
* **Slow** (``@pytest.mark.slow``): a/δ = 6, D = 4·a, δ/px = 3: ~1500
  conductor pixels, ~1.5 s solve. Asserts ±10%.
* **Resolution warning**: dedicated test asserting that δ/px < 30 trips
  ``rs_low_confidence``. **Conductor-separation warning**: dedicated test
  asserting that very close wires trip the same flag with the atlc2-style
  message.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from lineforge.analytical._constants import MU0
from lineforge.geometry.usermap import Usermap, UsermapMetadata
from lineforge.solvers.faraday import solve_lrs
from tests.fixtures.geometries import build_wire_pair_usermap

RHO_CU: float = 1.7241e-8


def _skin_depth(frequency_hz: float, rho: float = RHO_CU) -> float:
    omega = 2.0 * math.pi * frequency_hz
    return math.sqrt(2.0 * rho / (omega * MU0))


def _wire_pair_rs_analytic(a: float, delta: float, rho: float = RHO_CU) -> float:
    """Total loop Rs for a two-wire differential pair: 2 × per-wire surface Rs."""
    sigma = 1.0 / rho
    per_wire = 1.0 / (sigma * delta * 2.0 * math.pi * a)
    return 2.0 * per_wire


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLC3_NO_CACHE", "1")


class TestRoundWirePairAcRsFast:
    """Smoke-grade parity that runs every CI commit."""

    def test_ac_rs_matches_analytical_within_20pct(self) -> None:
        """Two copper wires at 1 GHz: loop R_per_m within ±20% of 2·R_per_wire."""
        f = 1.0e9
        delta = _skin_depth(f)

        delta_px_ratio = 3
        px = delta / delta_px_ratio
        a = 3.0 * delta
        D = 4.0 * a  # well-separated → no close-conductor warning

        usermap = build_wire_pair_usermap(a, D, pixel_width_m=px, margin_pixels=4)
        # No skin masking: at a = 3·δ the masking would leave the wires solid
        # anyway. Letting the solver carry all wire pixels gives the most direct
        # comparison to the surface-current formula.
        result = solve_lrs(usermap, frequency_hz=f, method="dense")

        r_analytic = _wire_pair_rs_analytic(a, delta)
        ratio = result.R_per_m / r_analytic
        assert 0.80 <= ratio <= 1.20, (
            f"Wire-pair AC Rs ratio {ratio:.3f} outside ±20% band. "
            f"solver={result.R_per_m:.3e} Ω/m, analytical={r_analytic:.3e} Ω/m, "
            f"a={a * 1e6:.2f}µm, D={D * 1e6:.2f}µm, δ={delta * 1e6:.2f}µm, "
            f"n_conductor_pixels={result.n_conductor_pixels}."
        )

    def test_resolution_warning_fires_below_30_px(self) -> None:
        """δ/px < 30 ⇒ ``rs_low_confidence`` flag + skin-depth-resolution message.

        Validates the warning machinery introduced for Workstream C-#9.
        """
        f = 1.0e9
        delta = _skin_depth(f)
        # δ/px = 5: clearly under the 30-px target → should flag.
        px = delta / 5.0
        a = 3.0 * delta
        D = 4.0 * a

        usermap = build_wire_pair_usermap(a, D, pixel_width_m=px, margin_pixels=4)
        result = solve_lrs(usermap, frequency_hz=f, method="dense")

        assert result.rs_low_confidence is True
        assert result.rs_warning is not None
        msg = result.rs_warning.lower()
        assert "skin depth" in msg
        assert "30" in result.rs_warning  # references the 30-px target
        # The message must point users at a concrete remedy.
        assert "pixel_width" in msg or "frequency" in msg

    def test_close_conductor_warning_still_fires(self) -> None:
        """Separation < 8 px ⇒ the legacy atlc2-style flag still triggers.

        Confirms the new δ/px check did not regress the older conductor-spacing
        check from ``_check_rs_geometry``.
        """
        # Build a synthetic two-strip usermap with the strips only 4 px apart.
        h, w = 12, 20
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)  # white = vacuum
        rgb[5:7, 4:8] = (255, 0, 0)  # +1 conductor
        rgb[5:7, 12:16] = (0, 0, 255)  # -1 conductor (4 px gap)
        usermap = Usermap(rgb, UsermapMetadata(pixel_width_m=1.0e-4))

        # Use a tiny frequency so the δ/px check is independent (δ for 1 Hz is
        # enormous, δ/px ≫ 30, so only the separation rule should fire).
        result = solve_lrs(usermap, frequency_hz=1.0, method="dense")
        assert result.rs_low_confidence is True
        assert result.rs_warning is not None
        assert "pixels apart" in result.rs_warning


@pytest.mark.slow
class TestRoundWirePairAcRsSlow:
    """Tighter tolerance on a larger grid. Skipped in fast CI runs."""

    def test_ac_rs_matches_analytical_within_10pct(self) -> None:
        """a/δ = 6, D = 4·a, δ/px = 3. Asserts ±10%."""
        f = 1.0e9
        delta = _skin_depth(f)

        delta_px_ratio = 3
        px = delta / delta_px_ratio
        a = 6.0 * delta
        D = 4.0 * a

        usermap = build_wire_pair_usermap(a, D, pixel_width_m=px, margin_pixels=4)
        result = solve_lrs(usermap, frequency_hz=f, method="dense")

        r_analytic = _wire_pair_rs_analytic(a, delta)
        ratio = result.R_per_m / r_analytic
        assert 0.90 <= ratio <= 1.10, (
            f"Wire-pair AC Rs ratio {ratio:.3f} outside ±10% band on the slow grid. "
            f"solver={result.R_per_m:.3e} Ω/m, analytical={r_analytic:.3e} Ω/m, "
            f"n_conductor_pixels={result.n_conductor_pixels}."
        )
