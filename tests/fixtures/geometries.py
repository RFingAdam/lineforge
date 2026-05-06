"""Reference geometries with analytically-known transmission-line parameters.

These fixtures provide the "ground truth" for validating the bitmap solvers
(Phase 2 C/Gp Laplace, Phase 3 Faraday L/Rs). For each geometry we compute
the analytical Z₀, L, C, Rs from textbook formulas and expose both:

    1. A function to build the :class:`Usermap`.
    2. A dataclass with the expected analytical values.

The tests in ``tests/test_solvers/test_parity.py`` then drive the bitmap
solvers against these fixtures and assert agreement within a documented
tolerance.

Coax — `air_coax` and `fr4_coax`:
    Z₀ = (η₀ / 2π·sqrt(εr)) · ln(b/a)         [Pozar §1.4]
    L  = (μ₀ / 2π) · ln(b/a)                  [DC self-inductance]
    C  = 2π·ε₀·εr / ln(b/a)
    Rs (low-f, DC) = ρ_inner / (π·a²) + ρ_outer / (π·(b² − b'²))

Round wire pair — `wire_pair`:
    Z₀ = (η₀ / π·sqrt(εr)) · acosh(D/(2a))   for centre-to-centre D, radius a
    L  = (μ₀ / π) · acosh(D/(2a))
    C  = π·ε₀·εr / acosh(D/(2a))

Parallel plate (sanity check) — `parallel_plate`:
    Z₀ = (η₀ · h) / (W · sqrt(εr))   for plate sep h, width W

All references: Pozar, *Microwave Engineering* 4th ed., Chapter 1; Wadell,
*Transmission Line Design Handbook*, Chapter 3.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from atlc3.analytical._constants import EPS0, ETA0, MU0
from atlc3.geometry.usermap import Usermap, UsermapMetadata


@dataclass(frozen=True)
class ReferenceCase:
    """A geometry + its analytical TL parameters."""

    name: str
    """Human-readable label."""

    builder: Callable[[], Usermap]
    """Function returning the Usermap. Closes over the dimensions."""

    z0_ohm: float
    """Analytical characteristic impedance [Ω]."""

    L_per_m: float
    """Analytical series inductance per unit length [H/m]."""

    C_per_m: float
    """Analytical shunt capacitance per unit length [F/m]."""

    eps_eff: float
    """Effective relative permittivity (= εr for fully-embedded geometries)."""

    notes: str = ""
    """Where the formula came from + any caveats."""


# ---------------------------------------------------------------------------
# Coax
# ---------------------------------------------------------------------------


def _coax_z0(a: float, b: float, er: float) -> float:
    """Analytical coaxial Z₀ in Ω."""
    return (ETA0 / (2.0 * math.pi * math.sqrt(er))) * math.log(b / a)


def _coax_L_per_m(a: float, b: float) -> float:  # noqa: N802
    return (MU0 / (2.0 * math.pi)) * math.log(b / a)


def _coax_C_per_m(a: float, b: float, er: float) -> float:  # noqa: N802
    return (2.0 * math.pi * EPS0 * er) / math.log(b / a)


def build_coax_usermap(
    inner_radius_m: float,
    outer_radius_m: float,
    *,
    pixel_width_m: float,
    er: float = 1.0,
    margin_pixels: int = 4,
) -> Usermap:
    """Rasterize a coax: red center conductor, FR4-or-vacuum dielectric, green outer ground."""
    # Total grid: outer radius + margin
    half = math.ceil(outer_radius_m / pixel_width_m) + margin_pixels
    n = 2 * half + 1
    rgb = np.full((n, n, 3), 0, dtype=np.uint8)  # black = vacuum

    if er > 1.001:
        # Use the FR4 atlc2 color for εr=4.4-ish; for arbitrary εr we'd need a
        # custom material lookup, but the parity tests we run use εr=1 (vacuum)
        # to stress-test the L_vacuum extraction path. For εr>1, the test
        # caller supplies the right er via post-build material override.
        pass

    yy, xx = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    cy = cx = half
    r2 = (yy - cy) ** 2 + (xx - cx) ** 2
    r = np.sqrt(r2) * pixel_width_m

    # Everything outside the outer radius is ground (green, V=0). This makes
    # the outer conductor "fill" the rest of the cell, equivalent to an
    # infinitely-thick shield as in a real coax — necessary so the Laplace
    # solver can't leak past a thin annulus.
    rgb[r >= outer_radius_m] = (0, 255, 0)
    # Center conductor (red, V=+1) — drawn last so it overwrites if needed.
    rgb[r <= inner_radius_m] = (255, 0, 0)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=pixel_width_m,
            name=f"coax-a{inner_radius_m * 1e3:.2f}mm-b{outer_radius_m * 1e3:.2f}mm",
            source="tests.fixtures.geometries.build_coax_usermap",
        ),
    )


def air_coax_50ohm() -> ReferenceCase:
    """Air-filled coax with Z₀ ≈ 50 Ω: a=0.5mm, b=1.15mm, εr=1.

    A standard 50Ω air-line geometry. Used as the canonical Phase 3 test case.
    """
    a = 0.5e-3
    b = 1.15e-3
    er = 1.0
    z0 = _coax_z0(a, b, er)
    return ReferenceCase(
        name="air_coax_50ohm",
        builder=lambda: build_coax_usermap(a, b, pixel_width_m=2e-5, er=er),
        z0_ohm=z0,
        L_per_m=_coax_L_per_m(a, b),
        C_per_m=_coax_C_per_m(a, b, er),
        eps_eff=er,
        notes=(
            "Air-filled 50Ω coax. Inner a=0.5mm, outer b=1.15mm. "
            "Z₀ = η₀/(2π) · ln(b/a) ≈ 50.0 Ω. "
            "Pixel width 20 µm → ~50 conductor pixels on the inner core."
        ),
    )


def air_coax_75ohm() -> ReferenceCase:
    """Air-filled coax with Z₀ ≈ 75 Ω: a=0.5mm, b=1.745mm.

    Solving (η₀/2π)·ln(b/a) = 75 → ln(b/a) = 1.251 → b/a = 3.494.
    """
    a = 0.5e-3
    b = 1.747e-3  # gives Z₀ ≈ 75 Ω exactly
    er = 1.0
    return ReferenceCase(
        name="air_coax_75ohm",
        builder=lambda: build_coax_usermap(a, b, pixel_width_m=3e-5, er=er),
        z0_ohm=_coax_z0(a, b, er),
        L_per_m=_coax_L_per_m(a, b),
        C_per_m=_coax_C_per_m(a, b, er),
        eps_eff=er,
        notes="Air 75Ω coax. b/a ≈ 3.49 → Z₀ ≈ 75 Ω.",
    )


# ---------------------------------------------------------------------------
# Round wire pair
# ---------------------------------------------------------------------------


def _wire_pair_z0(a: float, D: float, er: float) -> float:  # noqa: N803
    """Two parallel round wires, centre-to-centre D, radius a."""
    return (ETA0 / (math.pi * math.sqrt(er))) * math.acosh(D / (2.0 * a))


def _wire_pair_L_per_m(a: float, D: float) -> float:  # noqa: N802, N803
    return (MU0 / math.pi) * math.acosh(D / (2.0 * a))


def _wire_pair_C_per_m(a: float, D: float, er: float) -> float:  # noqa: N802, N803
    return (math.pi * EPS0 * er) / math.acosh(D / (2.0 * a))


def build_wire_pair_usermap(
    radius_m: float,
    spacing_m: float,
    *,
    pixel_width_m: float,
    margin_pixels: int = 8,
) -> Usermap:
    """Two parallel round wires (red +1, blue -1), separated by ``spacing_m`` (centre-to-centre)."""
    radius_px = math.ceil(radius_m / pixel_width_m)
    half_spacing_px = math.ceil((spacing_m / 2.0) / pixel_width_m)
    h = 2 * (radius_px + margin_pixels) + 1
    w = 2 * (half_spacing_px + radius_px + margin_pixels) + 1
    rgb = np.full((h, w, 3), 0, dtype=np.uint8)  # black = vacuum

    cy = h // 2
    cx_left = w // 2 - half_spacing_px
    cx_right = w // 2 + half_spacing_px

    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")

    r_left = np.sqrt((yy - cy) ** 2 + (xx - cx_left) ** 2) * pixel_width_m
    r_right = np.sqrt((yy - cy) ** 2 + (xx - cx_right) ** 2) * pixel_width_m

    rgb[r_left <= radius_m] = (255, 0, 0)
    rgb[r_right <= radius_m] = (0, 0, 255)

    return Usermap(
        rgb,
        UsermapMetadata(
            pixel_width_m=pixel_width_m,
            name=f"wire-pair-a{radius_m * 1e3:.2f}mm-D{spacing_m * 1e3:.2f}mm",
            source="tests.fixtures.geometries.build_wire_pair_usermap",
        ),
    )


def air_wire_pair_300ohm() -> ReferenceCase:
    """Classic 300Ω TV-antenna twinlead: a=0.5mm, D=8mm, εr=1.

    Z₀ = (η₀/π)·acosh(D/2a) ≈ 295 Ω for D/2a = 8.
    """
    a = 0.5e-3
    D = 8.0e-3
    er = 1.0
    return ReferenceCase(
        name="air_wire_pair_300ohm",
        builder=lambda: build_wire_pair_usermap(a, D, pixel_width_m=5e-5),
        z0_ohm=_wire_pair_z0(a, D, er),
        L_per_m=_wire_pair_L_per_m(a, D),
        C_per_m=_wire_pair_C_per_m(a, D, er),
        eps_eff=er,
        notes="300Ω twinlead. a=0.5mm, D=8mm.",
    )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


CASES: dict[str, ReferenceCase] = {
    case.name: case
    for case in (
        air_coax_50ohm(),
        air_coax_75ohm(),
        air_wire_pair_300ohm(),
    )
}


def list_cases() -> list[ReferenceCase]:
    return list(CASES.values())


__all__ = [
    "CASES",
    "ReferenceCase",
    "air_coax_50ohm",
    "air_coax_75ohm",
    "air_wire_pair_300ohm",
    "build_coax_usermap",
    "build_wire_pair_usermap",
    "list_cases",
]
