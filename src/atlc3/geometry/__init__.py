"""Geometry types and rasterizers.

Phase 1 ships all 7 standard PCB geometries as Pydantic models. Phase 2 adds
:class:`Usermap` and rasterizers that convert these models into bitmap grids
for the numerical solvers.
"""

from __future__ import annotations

from typing import Any

from atlc3.geometry.types import (
    GEOMETRY_TYPES,
    CPWG,
    BroadsideCoupledDiffStripline,
    EdgeCoupledDiffMicrostrip,
    EdgeCoupledDiffStripline,
    EmbeddedMicrostrip,
    GeometryUnion,
    Microstrip,
    StriplineAsymmetric,
    StriplineSymmetric,
)


def export_jsonschema() -> dict[str, Any]:
    """Return a JSON Schema covering every supported geometry.

    Used by the MCP server's ``describe_geometry`` tool to advertise input shapes
    to clients.
    """
    return {
        "title": "atlc3 geometry",
        "description": "Discriminated union of supported transmission line geometries.",
        "oneOf": [model.model_json_schema() for model in GEOMETRY_TYPES.values()],
        "discriminator": {"propertyName": "type"},
    }


def from_dict(data: dict[str, Any]) -> GeometryUnion:
    """Construct the right geometry model from a dict, dispatching on ``type``.

    Parameters
    ----------
    data
        Mapping with at least a ``type`` key whose value is one of the keys
        of :data:`atlc3.geometry.types.GEOMETRY_TYPES`.

    Raises
    ------
    KeyError
        If ``type`` is missing.
    ValueError
        If ``type`` is not a recognized geometry.
    """
    if "type" not in data:
        raise KeyError("'type' field is required to dispatch the geometry")

    geom_type = data["type"]
    if geom_type not in GEOMETRY_TYPES:
        raise ValueError(
            f"unknown geometry type {geom_type!r}; "
            f"valid types: {sorted(GEOMETRY_TYPES.keys())}"
        )

    model_class = GEOMETRY_TYPES[geom_type]
    return model_class.model_validate(data)  # type: ignore[return-value]


__all__ = [
    "BroadsideCoupledDiffStripline",
    "CPWG",
    "EdgeCoupledDiffMicrostrip",
    "EdgeCoupledDiffStripline",
    "EmbeddedMicrostrip",
    "GEOMETRY_TYPES",
    "GeometryUnion",
    "Microstrip",
    "StriplineAsymmetric",
    "StriplineSymmetric",
    "export_jsonschema",
    "from_dict",
]
