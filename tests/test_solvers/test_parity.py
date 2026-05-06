"""Parity tests — bitmap solvers vs analytical reference geometries.

These tests close the gap from AUDIT.md item #1: validate the C/Gp Laplace
solver and the Faraday L/Rs solver against geometries with known closed-form
answers (coax, wire pair).

Tolerances are wider than for the analytical solvers because:
    - The bitmap solver discretizes a continuous geometry on a finite grid.
    - Open-boundary truncation introduces systematic error proportional to
      the grid extent vs the field decay length.
    - For typical PCB-scale geometries the bitmap solver should land within
      5–15% of the analytical answer (closer to 5% for shielded geometries
      like coax, 15%-ish for unshielded like wire pair).

The analytical comparison values come from textbook formulas in
:mod:`tests.fixtures.geometries`.
"""

from __future__ import annotations

import math

import pytest

from atlc3.solvers.cgp import solve_cgp
from atlc3.solvers.faraday import solve_lrs as solve_lrs_faraday
from tests.fixtures.geometries import (
    CASES,
    air_coax_50ohm,
    air_coax_75ohm,
    air_wire_pair_300ohm,
)


# ---------------------------------------------------------------------------
# C/Gp solver vs analytical Z₀ and L
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestCGPParity:
    """Phase 2 C/Gp solver should reproduce the analytical Z₀ for shielded geometries.

    Coax is the canonical shielded case — the field is bounded by the outer
    conductor, so single-grid Laplace without aggressive boundary extension
    converges quickly and accurately.
    """

    def test_air_coax_50ohm(self) -> None:
        case = air_coax_50ohm()
        usermap = case.builder()
        result = solve_cgp(
            usermap,
            method="sor",
            tol=1e-5,
            max_iter=5000,
            extend_grid=False,  # coax is shielded; no extension needed
        )

        # ±10% on Z₀ — generous because the inner conductor is only ~25 px in radius
        assert math.isclose(result.z0, case.z0_ohm, rel_tol=0.10), (
            f"{case.name}: bitmap Z0={result.z0:.2f}Ω, "
            f"analytical={case.z0_ohm:.2f}Ω ({100 * abs(result.z0 - case.z0_ohm) / case.z0_ohm:.1f}% off)"
        )
        # ±10% on L
        assert math.isclose(result.L_per_m, case.L_per_m, rel_tol=0.10), (
            f"{case.name}: bitmap L={result.L_per_m * 1e9:.1f} nH/m, "
            f"analytical={case.L_per_m * 1e9:.1f} nH/m"
        )
        # ±10% on C
        assert math.isclose(result.C_per_m, case.C_per_m, rel_tol=0.10)

    def test_air_coax_75ohm(self) -> None:
        case = air_coax_75ohm()
        usermap = case.builder()
        result = solve_cgp(
            usermap,
            method="sor",
            tol=1e-5,
            max_iter=5000,
            extend_grid=False,
        )
        assert math.isclose(result.z0, case.z0_ohm, rel_tol=0.10), (
            f"75Ω coax: got Z0={result.z0:.2f}Ω, expected {case.z0_ohm:.2f}Ω"
        )

    def test_eps_eff_equals_one_for_air(self) -> None:
        """All air coax cases should report εeff ≈ 1.0 (vacuum)."""
        case = air_coax_50ohm()
        usermap = case.builder()
        result = solve_cgp(usermap, method="sor", tol=1e-5, max_iter=5000, extend_grid=False)
        # Vacuum cavity → εeff = 1.0; allow ±2% for grid discretization
        assert math.isclose(result.eps_eff, 1.0, rel_tol=0.02), (
            f"εeff for air coax = {result.eps_eff:.4f}, expected ~1.0"
        )


# ---------------------------------------------------------------------------
# Faraday L/Rs solver vs analytical L
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestFaradayParity:
    """Phase 3 Faraday/PEEC solver should reproduce the analytical DC inductance for coax + wire pair.

    These tests run at low frequency (1 MHz) to stay in the DC regime where
    skin effect doesn't yet redistribute the current — so the solver's L
    matches the textbook DC L = (μ₀/2π)·ln(b/a) for coax.
    """

    def test_coax_50ohm_dc_inductance(self) -> None:
        case = air_coax_50ohm()
        usermap = case.builder()
        # 1 MHz: skin depth ≫ conductor thickness → solver returns DC L
        result = solve_lrs_faraday(usermap, frequency_hz=1e6, method="dense")
        assert result.L_per_m > 0
        # ±20% — Faraday PEEC discretization on a small grid is approximate
        assert math.isclose(result.L_per_m, case.L_per_m, rel_tol=0.20), (
            f"50Ω coax DC L: got {result.L_per_m * 1e9:.1f} nH/m, "
            f"analytical {case.L_per_m * 1e9:.1f} nH/m "
            f"({100 * abs(result.L_per_m - case.L_per_m) / case.L_per_m:.1f}% off)"
        )

    def test_wire_pair_dc_inductance(self) -> None:
        case = air_wire_pair_300ohm()
        usermap = case.builder()
        result = solve_lrs_faraday(usermap, frequency_hz=1e6, method="dense")
        assert result.L_per_m > 0
        # ±25% for the wider-spaced wire-pair (more discretization error)
        assert math.isclose(result.L_per_m, case.L_per_m, rel_tol=0.25), (
            f"wire pair DC L: got {result.L_per_m * 1e9:.1f} nH/m, "
            f"analytical {case.L_per_m * 1e9:.1f} nH/m"
        )


# ---------------------------------------------------------------------------
# Smoke: catalog enumeration
# ---------------------------------------------------------------------------


def test_all_reference_cases_have_metadata() -> None:
    """Every catalog case should populate the analytical-truth dataclass fields."""
    for case in CASES.values():
        assert case.z0_ohm > 0
        assert case.L_per_m > 0
        assert case.C_per_m > 0
        assert case.eps_eff >= 1


def test_reference_z0_consistent_with_lc() -> None:
    """For each case, sqrt(L/C) should equal Z₀ (analytical consistency)."""
    for case in CASES.values():
        z0_from_lc = math.sqrt(case.L_per_m / case.C_per_m)
        assert math.isclose(z0_from_lc, case.z0_ohm, rel_tol=1e-9), (
            f"{case.name}: sqrt(L/C)={z0_from_lc:.4f}, z0_ohm={case.z0_ohm:.4f}"
        )
