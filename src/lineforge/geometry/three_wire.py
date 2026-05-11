"""3-conductor (3-wire) transmission-line geometry.

Three round conductors with arbitrary positions, optionally above an
infinite ground plane. The Y-decomposition formula (see
``docs/theory/three_wire.md``) reduces this to three pair-wise impedances
which combine into ZoR/ZoG/ZoB Y-legs and odd/even-mode impedances.

For the analytical solver (Phase B1) we use the method-of-images
inductance/capacitance matrix; for the bitmap solver (Phase B3) the
geometry is rasterized and routed through the floating-BC Laplace kernel
(Phase B2).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from lineforge.units import parse_length


def _normalize_length(value: object) -> object:
    if isinstance(value, str):
        return parse_length(value)
    return value


_Length = Annotated[float, BeforeValidator(_normalize_length), Field(gt=0)]
_Coord = Annotated[float, BeforeValidator(_normalize_length)]  # may be negative


class WirePosition(BaseModel):
    """Center coordinate of a single round conductor.

    The (x, y) origin is arbitrary — only relative positions matter. When
    a ground plane is present (``ThreeWireGeometry.ground_plane = True``),
    the plane sits at y = 0; conductor y-coordinates must therefore be
    > radius (so the conductor doesn't touch or intersect the ground).
    """

    model_config = ConfigDict(extra="forbid")

    x: _Coord = Field(..., description="Conductor center x-coordinate.")
    y: _Coord = Field(..., description="Conductor center y-coordinate.")


class ThreeWireGeometry(BaseModel):
    """Three round conductors of equal radius, optionally above a ground plane.

    The conductors are labeled by their atlc2 voltage roles:

    * ``red`` — the signal trace at V = +1
    * ``blue`` — the signal trace at V = −1
    * ``green`` — the third conductor (ground bridge, return wire, etc.)

    All three conductors share a common radius ``a``. The medium is uniform
    dielectric with relative permittivity ``er`` and loss tangent
    ``tan_delta``.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    type: Literal["three_wire"] = "three_wire"
    a: _Length = Field(..., description="Conductor radius (shared by all 3 wires).")

    red: WirePosition = Field(..., description="Position of the red (+1) conductor.")
    blue: WirePosition = Field(..., description="Position of the blue (-1) conductor.")
    green: WirePosition = Field(..., description="Position of the green (0) conductor.")

    er: float = Field(1.0, description="Uniform medium relative permittivity.", ge=1)
    tan_delta: float = Field(0.0, description="Uniform medium loss tangent.", ge=0)

    ground_plane: bool = Field(
        False,
        description=(
            "Whether an infinite ground plane sits at y=0 below the conductors. "
            "When True, all conductor y-coordinates must exceed ``a`` so they "
            "don't intersect the plane."
        ),
    )

    @model_validator(mode="after")
    def _validate_no_overlap_and_ground(self) -> ThreeWireGeometry:
        wires = {"red": self.red, "blue": self.blue, "green": self.green}
        # Pairwise non-overlap
        for name1, name2 in (("red", "blue"), ("red", "green"), ("blue", "green")):
            w1, w2 = wires[name1], wires[name2]
            d = ((w1.x - w2.x) ** 2 + (w1.y - w2.y) ** 2) ** 0.5
            if d <= 2 * self.a:
                raise ValueError(
                    f"ThreeWireGeometry: conductors {name1!r} and {name2!r} overlap "
                    f"(center-to-center {d:.3e} m, need > 2a = {2 * self.a:.3e} m)"
                )
        # Above-ground requirement
        if self.ground_plane:
            for name, w in wires.items():
                if w.y <= self.a:
                    raise ValueError(
                        f"ThreeWireGeometry: conductor {name!r} at y={w.y:.3e} m must "
                        f"sit above ground plane at y=0 with at least one radius "
                        f"({self.a:.3e} m) clearance"
                    )
        return self


__all__ = ["ThreeWireGeometry", "WirePosition"]
