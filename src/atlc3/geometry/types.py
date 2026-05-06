"""Pydantic geometry models for atlc3.0.

Each model is a self-contained spec for one transmission line cross-section.
Field validators check dimensional sanity. The MCP server auto-generates JSON
Schemas from these models for tool descriptions.

Naming convention: physics-style single-letter symbols (W, H, T, S, εr) are
used despite PEP 8, because that's what every PCB designer's mental model
expects. The ruff config ignores N803/N806/N802 in this package.

Distance fields (W, H, T, S, etc.) are ``Length`` — a Pydantic field type that
accepts a float (meters) or a unit-suffix string (``"6mil"``, ``"4mm"``,
``"30AWG"``). Strings are normalized to meters at validation time, so internal
storage is always SI base.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from atlc3.units import parse_length


def _normalize_length(value: object) -> object:
    """Pydantic BeforeValidator: parse unit strings to meters."""
    if isinstance(value, str):
        return parse_length(value)
    return value


Length = Annotated[float, BeforeValidator(_normalize_length), Field(gt=0)]
"""A length value in meters. Accepts unit strings on input."""


COPPER_RHO: float = 1.7241e-8  # Ω·m, atlc2 default for red/green/blue


class _BaseGeometry(BaseModel):
    """Common Pydantic configuration for all geometry models."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --- single-strip geometries ----------------------------------------------------


class Microstrip(_BaseGeometry):
    """Microstrip: a strip on top of a dielectric over a ground plane.

    ::

         ┌───────┐  ← strip (W wide, T thick)
         │       │
        ─┴───────┴─ ─ ─ ─ ─
          dielectric (H thick, εr)
         ──────────────────  ← ground plane

    """

    type: Literal["microstrip"] = "microstrip"
    W: Length = Field(..., description="Strip width.")
    H: Length = Field(..., description="Dielectric height.")
    T: Length = Field(..., description="Strip thickness.")
    er: float = Field(..., description="Relative permittivity of the dielectric.", ge=1)
    tan_delta: float = Field(0.0, description="Loss tangent of the dielectric.", ge=0)
    rho: float = Field(COPPER_RHO, description="Conductor resistivity [Ω·m].", gt=0)


class EmbeddedMicrostrip(_BaseGeometry):
    """Embedded (coated) microstrip: microstrip plus a coating dielectric on top.

    ::

         ╳╳╳╳╳╳╳╳╳╳╳╳╳╳  ← coating (H2 thick, er2)
         ╳╳┌──────┐╳╳╳
         ╳╳│      │╳╳╳
        ─┴─┴──────┴─┴─
            dielectric (H, er)
         ──────────────  ← ground plane

    """

    type: Literal["embedded_microstrip"] = "embedded_microstrip"
    W: Length = Field(..., description="Strip width.")
    H: Length = Field(..., description="Substrate dielectric height.")
    H2: Length = Field(..., description="Coating thickness above the strip.")
    T: Length = Field(..., description="Strip thickness.")
    er: float = Field(..., description="Substrate relative permittivity.", ge=1)
    er2: float = Field(..., description="Coating relative permittivity.", ge=1)
    tan_delta: float = Field(0.0, ge=0)
    tan_delta_2: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)


class StriplineSymmetric(_BaseGeometry):
    """Symmetric stripline: a strip centered between two ground planes.

    ::

         ──────────────  ← top ground
              ┌───┐      ← strip (W, T)
              │   │
         ──────────────  ← bottom ground

         B = total plate separation, dielectric fills it (er)
    """

    type: Literal["stripline_symmetric"] = "stripline_symmetric"
    W: Length = Field(..., description="Strip width.")
    T: Length = Field(..., description="Strip thickness.")
    B: Length = Field(..., description="Plate-to-plate separation.")
    er: float = Field(..., ge=1)
    tan_delta: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)


class StriplineAsymmetric(_BaseGeometry):
    """Asymmetric stripline: strip is offset from the midline between ground planes.

    H1 is the dielectric thickness above the strip, H2 below. The strip itself
    is at the boundary between H1 and H2; total cavity = H1 + T + H2.
    """

    type: Literal["stripline_asymmetric"] = "stripline_asymmetric"
    W: Length = Field(..., description="Strip width.")
    T: Length = Field(..., description="Strip thickness.")
    H1: Length = Field(..., description="Dielectric thickness above the strip.")
    H2: Length = Field(..., description="Dielectric thickness below the strip.")
    er: float = Field(..., ge=1)
    tan_delta: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)


class CPWG(_BaseGeometry):
    """Coplanar waveguide with ground plane (grounded coplanar waveguide).

    Center signal trace flanked by two coplanar ground rails (gap S each side),
    with a continuous ground plane H below.
    ::

         ████  ┌────┐  ████   ← top: coplanar grounds + signal (W)
              S│    │S        ← S is the gap to each side ground
         ─────┴────┴───────
              dielectric (H, er)
         ──────────────────   ← bottom ground plane
    """

    type: Literal["cpwg"] = "cpwg"
    W: Length = Field(..., description="Center signal trace width.")
    S: Length = Field(..., description="Gap from signal to each side ground.")
    H: Length = Field(..., description="Substrate height to bottom ground plane.")
    T: Length = Field(..., description="Conductor thickness.")
    er: float = Field(..., ge=1)
    tan_delta: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)


# --- differential geometries ----------------------------------------------------


class EdgeCoupledDiffMicrostrip(_BaseGeometry):
    """Edge-coupled differential pair (microstrip).

    Two parallel strips on top of a dielectric, separated by a gap S.
    """

    type: Literal["edge_coupled_diff_microstrip"] = "edge_coupled_diff_microstrip"
    W: Length = Field(..., description="Each strip's width.")
    S: Length = Field(..., description="Edge-to-edge gap between the two strips.")
    H: Length = Field(..., description="Dielectric height to ground plane.")
    T: Length = Field(..., description="Strip thickness.")
    er: float = Field(..., ge=1)
    tan_delta: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)


class EdgeCoupledDiffStripline(_BaseGeometry):
    """Edge-coupled differential pair (stripline).

    Two parallel strips centered between two ground planes (separation B),
    with edge-to-edge gap S in the dielectric (er).
    """

    type: Literal["edge_coupled_diff_stripline"] = "edge_coupled_diff_stripline"
    W: Length = Field(..., description="Each strip's width.")
    S: Length = Field(..., description="Edge-to-edge gap between the two strips.")
    B: Length = Field(..., description="Plate-to-plate separation.")
    T: Length = Field(..., description="Strip thickness.")
    er: float = Field(..., ge=1)
    tan_delta: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)


class BroadsideCoupledDiffStripline(_BaseGeometry):
    """Broadside-coupled differential pair (stripline).

    Two strips stacked vertically, separated by H_between of dielectric,
    centered between two ground planes.
    """

    type: Literal["broadside_coupled_diff_stripline"] = "broadside_coupled_diff_stripline"
    W: Length = Field(..., description="Strip width (both strips identical).")
    H1: Length = Field(..., description="Distance from each strip to the nearer ground.")
    H_between: Length = Field(..., description="Dielectric thickness between the two strips.")
    T: Length = Field(..., description="Strip thickness.")
    er: float = Field(..., ge=1)
    tan_delta: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)


# --- discriminated union --------------------------------------------------------

GeometryUnion = Union[  # noqa: UP007 — Pydantic discriminated union needs Union[]
    Microstrip,
    EmbeddedMicrostrip,
    StriplineSymmetric,
    StriplineAsymmetric,
    CPWG,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    BroadsideCoupledDiffStripline,
]
"""Discriminated union (on ``type``) covering every supported geometry.

Used as the input type for :func:`atlc3.analytical.solve` and the MCP server's
``calculate_impedance`` tool.
"""


GEOMETRY_TYPES: dict[str, type[BaseModel]] = {
    "microstrip": Microstrip,
    "embedded_microstrip": EmbeddedMicrostrip,
    "stripline_symmetric": StriplineSymmetric,
    "stripline_asymmetric": StriplineAsymmetric,
    "cpwg": CPWG,
    "edge_coupled_diff_microstrip": EdgeCoupledDiffMicrostrip,
    "edge_coupled_diff_stripline": EdgeCoupledDiffStripline,
    "broadside_coupled_diff_stripline": BroadsideCoupledDiffStripline,
}
"""Lookup table from ``type`` discriminator string to model class."""


__all__ = [
    "GEOMETRY_TYPES",
    "BroadsideCoupledDiffStripline",
    "CPWG",
    "COPPER_RHO",
    "EdgeCoupledDiffMicrostrip",
    "EdgeCoupledDiffStripline",
    "EmbeddedMicrostrip",
    "GeometryUnion",
    "Length",
    "Microstrip",
    "StriplineAsymmetric",
    "StriplineSymmetric",
]
