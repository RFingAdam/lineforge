"""Multi-layer dielectric stack support.

For real PCB stackups, the dielectric on either side of a stripline trace is
often a stack of multiple layers (Prepreg + voided plane + Core, for example,
when an intermediate plane is voided to push the reference down to the next
layer). This module provides:

- :class:`DielectricLayer` — a single layer (thickness, εr, loss tangent).
- :func:`series_reduce` — collapse a stack into a single equivalent
  ``(h_total, εr_eq, tan_δ_eq)`` using the parallel-plate (series-capacitance)
  reduction. The result plugs directly into single-εr solver paths.

The math
--------
For a stack of N layers between two equipotential plates, each layer behaves
as a parallel-plate capacitor with per-area capacitance Cᵢ ∝ εᵢ / hᵢ. The
layers are in series (same charge, voltage divides), so::

    1/C_eq = Σᵢ (1/Cᵢ)  ⇒  C_eq ∝ 1 / Σᵢ (hᵢ / εᵢ)

We define an equivalent single layer of total thickness ``h_total = Σ hᵢ`` and
an effective permittivity ``εr_eq`` that produces the same C_eq::

    εr_eq = h_total / Σᵢ (hᵢ / εᵢ)

For the loss tangent, dissipated power per layer is Pᵢ ∝ Vᵢ² × ω × Cᵢ × tanᵢ.
For a series stack with constant charge Q, Vᵢ = Q × hᵢ / (ε₀ × εᵢ × A), giving
Pᵢ ∝ Q² × ω × tanᵢ × hᵢ / εᵢ. Equating to a single equivalent layer::

    tan_δ_eq = Σᵢ (tanᵢ × hᵢ / εᵢ) / Σᵢ (hᵢ / εᵢ)

i.e. a weighted average of tan_δᵢ with weights ``wᵢ = hᵢ / εᵢ``. This is the
correct dual to the C-weighted (parallel) average used at the two-half-stripline
level in :func:`atlc3.analytical.wadell.stripline_asymmetric`.

Reference: Pozar §3.5 "Dielectric Loss," Wadell §3.5.4 "Multi-layer dielectrics."
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from atlc3.units import parse_length


def _normalize_length(value: object) -> object:
    if isinstance(value, str):
        return parse_length(value)
    return value


_LayerLength = Annotated[float, BeforeValidator(_normalize_length), Field(gt=0)]


class DielectricLayer(BaseModel):
    """A single layer in a stratified dielectric stack.

    Attributes
    ----------
    h : Length
        Thickness in meters (or unit string such as ``"5.3mil"``).
    er : float
        Relative permittivity (≥ 1).
    tan_delta : float
        Loss tangent at the operating frequency (≥ 0; default 0).
    name : str | None
        Optional human-readable label (e.g. ``"Prepreg 1080"``,
        ``"Megtron 6 Core"``). Used by the rasterizer to build descriptive
        material records and by GUIs for display.
    """

    model_config = ConfigDict(extra="forbid")

    h: _LayerLength = Field(..., description="Layer thickness.")
    er: float = Field(..., description="Relative permittivity.", ge=1)
    tan_delta: float = Field(0.0, description="Loss tangent.", ge=0)
    name: str | None = Field(None, description="Optional label.")


def series_reduce(layers: list[DielectricLayer]) -> tuple[float, float, float]:
    """Collapse a series-stack of dielectric layers to a single equivalent.

    Parameters
    ----------
    layers
        Non-empty list of :class:`DielectricLayer`. Order does not affect the
        electrical reduction (series caps commute).

    Returns
    -------
    (h_total, er_eq, tan_eq)
        Total thickness in meters; capacitance-weighted εr equivalent;
        loss-tangent-weighted equivalent.

    Raises
    ------
    ValueError
        If the layer list is empty.

    Examples
    --------
    The L3 SIG1 void-L4 case from this session::

        >>> from atlc3.geometry.dielectric import DielectricLayer, series_reduce
        >>> layers = [
        ...     DielectricLayer(h="5.3mil", er=3.7, tan_delta=0.020),  # Prepreg
        ...     DielectricLayer(h="1.4mil", er=3.7, tan_delta=0.020),  # voided L4
        ...     DielectricLayer(h="3.5mil", er=4.2, tan_delta=0.020),  # Core
        ... ]
        >>> h_total, er_eq, tan_eq = series_reduce(layers)
        >>> round(er_eq, 3)
        3.858

    A single layer reduces to itself (no math needed)::

        >>> h, er, tan = series_reduce([DielectricLayer(h="3mil", er=4.2, tan_delta=0.01)])
        >>> round(er, 3), round(tan, 3)
        (4.2, 0.01)
    """
    if not layers:
        raise ValueError("series_reduce requires at least one layer")

    if len(layers) == 1:
        only = layers[0]
        return only.h, only.er, only.tan_delta

    h_total = sum(layer.h for layer in layers)
    inv_er_sum = sum(layer.h / layer.er for layer in layers)
    er_eq = h_total / inv_er_sum

    tan_weighted = sum(layer.tan_delta * layer.h / layer.er for layer in layers)
    tan_eq = tan_weighted / inv_er_sum

    return h_total, er_eq, tan_eq


__all__ = ["DielectricLayer", "series_reduce"]
