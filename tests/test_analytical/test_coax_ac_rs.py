"""Phase 3 AC Rs parity: Faraday/PEEC solver vs analytical skin-effect formula for coax.

Closes the AC Rs parity gap flagged in ``AUDIT.md`` (Workstream C-#9). The DC L
side of the coax fixture is already validated in
``tests/test_solvers/test_parity.py``; here we drive the same air-coax geometry
at 1 GHz and assert the solver's ``R_per_m`` matches the closed-form

    R_s = (1/(σ·δ)) · (1/(2π·a) + 1/(2π·b))   [Ω/m]

where ``δ = sqrt(2ρ / (ω·μ₀))`` is the copper skin depth, ``a`` is the inner-
conductor radius and ``b`` is the inner radius of the outer shield.

References
----------
* Pozar, *Microwave Engineering* 4th ed., §2.4 "Loss in a Coaxial Line".
* Ramo/Whinnery/Van Duzer, *Fields and Waves in Communication Electronics*
  3rd ed., §4.4: surface resistance of a good conductor.

Test budget
-----------
The Faraday solver is dense (``O(N²)`` memory) so the test grid cannot use the
audit's "δ ≥ 30·px" target while keeping conductor counts inside a reasonable
dense-solve budget. We use two tolerance tiers:

* **Fast** (no marker): small grid (a/δ ≈ 3, b/a = 2, δ/px = 3): ~1000
  conductor pixels post skin-mask, ~1 s solve. Asserts ±15%.
* **Slow** (``@pytest.mark.slow``): larger grid (a/δ ≈ 4, b/a = 3, δ/px = 4),
  ~1500 conductor pixels, ~2 s solve. Asserts ±10%.

Both tiers stay deep inside the skin regime (a > 3δ) so the surface-current
formula applies and the residual error is dominated by finite a/δ + finite
δ/px discretization.
"""

from __future__ import annotations

import math

import pytest

from lineforge.analytical._constants import MU0
from lineforge.solvers.faraday import solve_lrs
from lineforge.solvers.skin_depth import mask_skin_depth
from tests.fixtures.geometries import build_coax_usermap

# Copper resistivity used by the default lineforge material database. atlc2's DB
# stores ρ in µΩ·cm (1.7241 → 1.7241e-8 Ω·m). The Faraday solver picks this up
# automatically when the red/green/blue conductor pixels are placed by
# ``build_coax_usermap``.
RHO_CU: float = 1.7241e-8


def _skin_depth(frequency_hz: float, rho: float = RHO_CU) -> float:
    """Classical skin depth δ = sqrt(2ρ / (ωμ₀)) [m]."""
    omega = 2.0 * math.pi * frequency_hz
    return math.sqrt(2.0 * rho / (omega * MU0))


def _coax_rs_analytic(
    a: float,
    b: float,
    delta: float,
    rho: float = RHO_CU,
) -> float:
    """Per-unit-length AC Rs of a coax in the strong-skin limit (a, t_shield ≫ δ).

    R_s = (1/(σ·δ)) · (1/(2π·a) + 1/(2π·b))

    a: inner conductor radius
    b: outer shield inner radius
    """
    sigma = 1.0 / rho
    return (1.0 / (sigma * delta)) * (1.0 / (2.0 * math.pi * a) + 1.0 / (2.0 * math.pi * b))


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the solver disk cache for these tests.

    The Rs warning machinery was added after some legacy cache entries may have
    been written; bypass the cache so the fresh code path executes.
    """
    monkeypatch.setenv("ATLC3_NO_CACHE", "1")


class TestCoaxAcRsFast:
    """Smoke-grade parity that must run in CI on every commit."""

    def test_ac_rs_matches_analytical_within_15pct(self) -> None:
        """Air coax at 1 GHz: solver's R_per_m within ±15% of the surface formula."""
        f = 1.0e9
        delta = _skin_depth(f)

        # Grid setup: δ resolved by 3 px, a = 3·δ, b = 2·a. This keeps the
        # conductor count to ~1k post-mask and the dense solve under ~2 s.
        delta_px_ratio = 3
        px = delta / delta_px_ratio
        a = 3.0 * delta
        b = 2.0 * a

        usermap = build_coax_usermap(a, b, pixel_width_m=px, margin_pixels=2)
        # Skin mask hollows the inner conductor of any pixels deeper than 3·δ
        # from the surface; for a = 3·δ the inner stays solid (no harm).
        masked = mask_skin_depth(usermap, frequency_hz=f, factor=3.0)

        result = solve_lrs(masked, frequency_hz=f, method="dense")

        r_analytic = _coax_rs_analytic(a, b, delta)
        ratio = result.R_per_m / r_analytic
        assert 0.85 <= ratio <= 1.15, (
            f"AC Rs ratio {ratio:.3f} outside ±15% band. "
            f"solver={result.R_per_m:.3e} Ω/m, analytical={r_analytic:.3e} Ω/m, "
            f"a={a * 1e6:.2f}µm, b={b * 1e6:.2f}µm, δ={delta * 1e6:.2f}µm, "
            f"n_conductor_pixels={result.n_conductor_pixels}."
        )

    def test_low_resolution_triggers_warning(self) -> None:
        """δ/px ≪ 30 ⇒ ``rs_low_confidence`` flag + skin-depth message in warning."""
        f = 1.0e9
        delta = _skin_depth(f)

        # δ/px = 3: well under the 30-px target → should flag.
        px = delta / 3.0
        a = 3.0 * delta
        b = 2.0 * a

        usermap = build_coax_usermap(a, b, pixel_width_m=px, margin_pixels=2)
        result = solve_lrs(usermap, frequency_hz=f, method="dense")

        assert result.rs_low_confidence is True
        assert result.rs_warning is not None
        # The new check identifies itself with "skin depth" / δ wording.
        assert "skin depth" in result.rs_warning.lower()
        assert "30" in result.rs_warning  # references the 30-px target


@pytest.mark.slow
class TestCoaxAcRsSlow:
    """Tighter tolerance on a larger grid. Skipped in fast CI runs."""

    def test_ac_rs_matches_analytical_within_10pct(self) -> None:
        """Air coax with a/δ = 4, b/a = 3, δ/px = 4. Asserts ±10%."""
        f = 1.0e9
        delta = _skin_depth(f)

        delta_px_ratio = 4
        px = delta / delta_px_ratio
        a = 4.0 * delta
        b = 3.0 * a  # b/a = 3 → ln(b/a) ≈ 1.10, well-conditioned for the formula

        usermap = build_coax_usermap(a, b, pixel_width_m=px, margin_pixels=2)
        masked = mask_skin_depth(usermap, frequency_hz=f, factor=3.0)

        result = solve_lrs(masked, frequency_hz=f, method="dense")

        r_analytic = _coax_rs_analytic(a, b, delta)
        ratio = result.R_per_m / r_analytic
        assert 0.90 <= ratio <= 1.10, (
            f"AC Rs ratio {ratio:.3f} outside ±10% band on the slow grid. "
            f"solver={result.R_per_m:.3e} Ω/m, analytical={r_analytic:.3e} Ω/m, "
            f"n_conductor_pixels={result.n_conductor_pixels}."
        )
