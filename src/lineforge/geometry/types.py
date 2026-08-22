"""Pydantic geometry models for lineforge.

Each model is a self-contained spec for one transmission line cross-section.
Field validators check dimensional sanity. The MCP server auto-generates JSON
Schemas from these models for tool descriptions.

Naming convention: physics-style single-letter symbols (W, H, T, S, εr) are
used despite PEP 8, because that's what every PCB designer's mental model
expects. The ruff config ignores N803/N806/N802 in this package.

Distance fields (W, H, T, S, etc.) are ``Length``. A Pydantic field type that
accepts a float (meters) or a unit-suffix string (``"6mil"``, ``"4mm"``,
``"30AWG"``). Strings are normalized to meters at validation time, so internal
storage is always SI base.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from lineforge.geometry.dielectric import DielectricLayer, series_reduce
from lineforge.units import parse_length


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

    For real PCB stackups where the dielectric above and below the strip differ
    (e.g. Core above, Prepreg below: common when routing on an inner signal
    layer between a plane and a power layer), pass ``er_above`` / ``er_below``
    (and optionally ``tan_delta_above`` / ``tan_delta_below``). When supplied,
    these override the single ``er`` / ``tan_delta`` values: the closed-form
    solver uses a capacitance-weighted εr_eff, and the bitmap rasterizer
    paints the two halves with different materials.

    For multi-layer stacks on either side (e.g. Prepreg + voided plane + Core
    when an intermediate plane is voided to push the reference down), pass
    ``stack_above`` / ``stack_below`` as a list of :class:`DielectricLayer`.
    The stack is series-reduced via the parallel-plate (C-series) formula
    ``εr_eq = h_total / Σ(hᵢ/εᵢ)`` to derive H1/H2/εr_above/εr_below
    automatically: the explicit per-side fields are then unused.
    """

    type: Literal["stripline_asymmetric"] = "stripline_asymmetric"
    W: Length = Field(..., description="Strip width.")
    T: Length = Field(..., description="Strip thickness.")
    H1: Length = Field(..., description="Dielectric thickness above the strip.")
    H2: Length = Field(..., description="Dielectric thickness below the strip.")
    er: float = Field(
        ...,
        description="Bulk relative permittivity (used when er_above/er_below not given).",
        ge=1,
    )
    tan_delta: float = Field(0.0, ge=0)
    rho: float = Field(COPPER_RHO, gt=0)
    er_above: float | None = Field(
        None,
        description="Optional εr of the dielectric above the strip (overrides er for that half).",
        ge=1,
    )
    er_below: float | None = Field(
        None,
        description="Optional εr of the dielectric below the strip (overrides er for that half).",
        ge=1,
    )
    tan_delta_above: float | None = Field(
        None,
        description="Optional loss tangent above the strip.",
        ge=0,
    )
    tan_delta_below: float | None = Field(
        None,
        description="Optional loss tangent below the strip.",
        ge=0,
    )
    stack_above: list[DielectricLayer] | None = Field(
        None,
        description=(
            "Optional multi-layer dielectric stack above the strip. When set, "
            "H1, er_above and tan_delta_above are derived from the stack via "
            "C-series reduction; do not also pass H1/er_above/tan_delta_above "
            "explicitly."
        ),
    )
    stack_below: list[DielectricLayer] | None = Field(
        None,
        description=(
            "Optional multi-layer dielectric stack below the strip. When set, "
            "H2, er_below and tan_delta_below are derived from the stack."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_h_from_stacks(cls, data: Any) -> Any:
        """Pre-fill H1/er_above/tan_delta_above (and below) from stacks if given.

        Runs in 'before' mode so the derived values pass through the normal
        Length / float field validators downstream. Also fills the bulk ``er``
        field with the larger of the two stack-derived εr_eq values (it acts
        only as a fallback once split-εr fields are populated, but Pydantic
        still requires it to be ≥ 1).
        """
        if not isinstance(data, dict):
            return data

        any_stack = False
        for side, h_key, er_key, tan_key in (
            ("stack_above", "H1", "er_above", "tan_delta_above"),
            ("stack_below", "H2", "er_below", "tan_delta_below"),
        ):
            stack = data.get(side)
            if not stack:
                continue
            any_stack = True
            # Allow either DielectricLayer instances or plain dicts.
            layers = [
                layer if isinstance(layer, DielectricLayer) else DielectricLayer(**layer)
                for layer in stack
            ]
            h_total, er_eq, tan_eq = series_reduce(layers)
            for k, v in ((h_key, h_total), (er_key, er_eq), (tan_key, tan_eq)):
                existing = data.get(k)
                if existing not in (None, 0, 0.0):
                    # Allow the model_dump → model_validate_json round-trip:
                    # the dump emits both ``stack_below`` and the derived
                    # ``H2``/``er_below``/``tan_delta_below``. Accept exact
                    # numerical agreement; reject genuine inconsistencies.
                    if isinstance(existing, (int, float)) and abs(existing - v) <= max(
                        1e-9 * abs(v), 1e-12
                    ):
                        continue
                    raise ValueError(
                        f"StriplineAsymmetric: cannot pass both {side} and {k}; "
                        f"the stack derives {k} automatically."
                    )
                data[k] = v
            # Materialize the validated layers back into the dict so the field
            # type sees DielectricLayer instances (not raw dicts).
            data[side] = layers

        # When at least one stack is given, ``er`` is unused (er_above/er_below
        # take over) but Pydantic still requires er ≥ 1. Default it to the
        # larger derived εr_eq so it's at least dimensionally sensible.
        if any_stack and "er" not in data:
            candidates = [data.get("er_above"), data.get("er_below")]
            data["er"] = max(c for c in candidates if c is not None)
        return data


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

Used as the input type for :func:`lineforge.analytical.solve` and the MCP server's
``calculate_impedance`` tool.
"""


def _register_three_wire() -> dict[str, type[BaseModel]]:
    """Lazy import to avoid circular references on module load."""
    from lineforge.geometry.three_wire import ThreeWireGeometry

    return {"three_wire": ThreeWireGeometry}


GEOMETRY_TYPES: dict[str, type[BaseModel]] = {
    "microstrip": Microstrip,
    "embedded_microstrip": EmbeddedMicrostrip,
    "stripline_symmetric": StriplineSymmetric,
    "stripline_asymmetric": StriplineAsymmetric,
    "cpwg": CPWG,
    "edge_coupled_diff_microstrip": EdgeCoupledDiffMicrostrip,
    "edge_coupled_diff_stripline": EdgeCoupledDiffStripline,
    "broadside_coupled_diff_stripline": BroadsideCoupledDiffStripline,
    **_register_three_wire(),
}
"""Lookup table from ``type`` discriminator string to model class."""


__all__ = [
    "COPPER_RHO",
    "CPWG",
    "GEOMETRY_TYPES",
    "BroadsideCoupledDiffStripline",
    "EdgeCoupledDiffMicrostrip",
    "EdgeCoupledDiffStripline",
    "EmbeddedMicrostrip",
    "GeometryUnion",
    "Length",
    "Microstrip",
    "StriplineAsymmetric",
    "StriplineSymmetric",
]
