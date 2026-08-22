"""atlc2 default material database: 45 colors with their physical properties.

Source: atlc2 manual, http://www.hdtvprimer.com/kq6qv/atlc2.html: table of
"standard (internally defined) colors". Phase 2 extends this with the
``MoreColors.txt`` parser (:mod:`lineforge.materials.morecolors`) for user-defined
materials.

Each :class:`MaterialRecord` is keyed by the (R, G, B) tuple so a usermap pixel
can be looked up directly.

Use:
    - ``+1`` / ``-1`` / ``0`` / ``float`` for conductors (the V boundary condition).
    - ``insul`` for dielectrics.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MaterialUse = Literal["+1", "-1", "0", "float", "insul"]


class MaterialRecord(BaseModel):
    """A single material entry in the atlc2-style database.

    For modern high-frequency laminates whose Dk and Df vary with frequency,
    the optional ``er_freq`` / ``tan_freq`` mappings carry the per-frequency
    tabulated values. When supplied, :func:`lineforge.materials.dispersion.
    material_at_frequency` interpolates them log-linearly; otherwise the
    constant ``er`` / ``tan_delta`` fields are used as fallback.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rgb: tuple[int, int, int] = Field(..., description="(R, G, B) tuple, each 0-255.")
    use: MaterialUse = Field(..., description="Conductor (+1/-1/0/float) or insulator role.")
    resistivity_ohm_cm: float = Field(
        1.7241,
        description="Resistivity [Ω·cm]. atlc2 uses cm for legacy reasons.",
        ge=0,
    )
    er: float = Field(1.0, description="Relative permittivity (1.0 for conductors).", ge=1)
    tan_delta: float = Field(0.0, description="Loss tangent (0 for conductors).", ge=0)
    mu_r: float = Field(1.0, description="Relative permeability (1.0 for non-magnetic).", ge=0)
    name: str = Field(..., description="Human-readable material name.")
    er_freq: dict[float, float] | None = Field(
        None,
        description=(
            "Optional Dk(f) table {Hz: εr}. When set, interpolated log-linearly "
            "in frequency; the constant ``er`` is used as fallback."
        ),
    )
    tan_freq: dict[float, float] | None = Field(
        None,
        description="Optional Df(f) table {Hz: tan_δ}. Same semantics as er_freq.",
    )

    @property
    def is_conductor(self) -> bool:
        """True if this is a conductor pixel (+1/-1/0/float)."""
        return self.use != "insul"

    @property
    def is_insulator(self) -> bool:
        """True if this is an insulator/dielectric pixel."""
        return self.use == "insul"

    @property
    def voltage_bc(self) -> float | None:
        """Dirichlet V-boundary value for the C/Gp Laplace solver, or None for floating/insulator.

        Floating and insulator pixels have no fixed Dirichlet BC; the Laplace
        solver lets them settle to whatever the field demands.
        """
        return {"+1": 1.0, "-1": -1.0, "0": 0.0}.get(self.use)

    def at_frequency(self, freq_hz: float) -> tuple[float, float]:
        """Evaluate (εr, tan_δ) at a specific frequency.

        If this record has ``er_freq`` / ``tan_freq`` tables, the values are
        interpolated log-linearly; otherwise the constant fields are returned.
        """
        from lineforge.materials.dispersion import material_at_frequency

        return material_at_frequency(
            er=self.er,
            tan_delta=self.tan_delta,
            er_freq=self.er_freq,
            tan_freq=self.tan_freq,
            freq_hz=freq_hz,
        )


# fmt: off
ATLC2_DEFAULTS: tuple[MaterialRecord, ...] = (
    # Conductors: copper variants
    MaterialRecord(rgb=(255, 0, 0),   use="+1",    resistivity_ohm_cm=1.7241, er=1, tan_delta=0, mu_r=1, name="copper"),
    MaterialRecord(rgb=(0, 255, 0),   use="0",     resistivity_ohm_cm=1.7241, er=1, tan_delta=0, mu_r=1, name="copper"),
    MaterialRecord(rgb=(0, 0, 255),   use="-1",    resistivity_ohm_cm=1.7241, er=1, tan_delta=0, mu_r=1, name="copper"),
    MaterialRecord(rgb=(0, 255, 255), use="float", resistivity_ohm_cm=1.7241, er=1, tan_delta=0, mu_r=1, name="copper"),

    # Aluminum variants
    MaterialRecord(rgb=(224, 31, 31),  use="+1",    resistivity_ohm_cm=2.62, er=1, tan_delta=0, mu_r=1, name="aluminum"),
    MaterialRecord(rgb=(31, 224, 31),  use="0",     resistivity_ohm_cm=2.62, er=1, tan_delta=0, mu_r=1, name="aluminum"),
    MaterialRecord(rgb=(31, 31, 224),  use="-1",    resistivity_ohm_cm=2.62, er=1, tan_delta=0, mu_r=1, name="aluminum"),
    MaterialRecord(rgb=(31, 224, 224), use="float", resistivity_ohm_cm=2.62, er=1, tan_delta=0, mu_r=1, name="aluminum"),

    # Silver variants
    MaterialRecord(rgb=(224, 31, 0),   use="+1",    resistivity_ohm_cm=1.62, er=1, tan_delta=0, mu_r=1, name="silver"),
    MaterialRecord(rgb=(31, 224, 0),   use="0",     resistivity_ohm_cm=1.62, er=1, tan_delta=0, mu_r=1, name="silver"),
    MaterialRecord(rgb=(31, 0, 224),   use="-1",    resistivity_ohm_cm=1.62, er=1, tan_delta=0, mu_r=1, name="silver"),
    MaterialRecord(rgb=(31, 255, 224), use="float", resistivity_ohm_cm=1.62, er=1, tan_delta=0, mu_r=1, name="silver"),

    # Gold variants
    MaterialRecord(rgb=(224, 0, 31),   use="+1",    resistivity_ohm_cm=2.44, er=1, tan_delta=0, mu_r=1, name="gold"),
    MaterialRecord(rgb=(0, 224, 31),   use="0",     resistivity_ohm_cm=2.44, er=1, tan_delta=0, mu_r=1, name="gold"),
    MaterialRecord(rgb=(0, 31, 224),   use="-1",    resistivity_ohm_cm=2.44, er=1, tan_delta=0, mu_r=1, name="gold"),
    MaterialRecord(rgb=(0, 224, 224),  use="float", resistivity_ohm_cm=2.44, er=1, tan_delta=0, mu_r=1, name="gold"),

    # Steel variants (atlc2 cannot model ferromagnetic μr properly: kept for completeness)
    MaterialRecord(rgb=(224, 63, 63),  use="+1",    resistivity_ohm_cm=9.71, er=1, tan_delta=0, mu_r=1, name="steel"),
    MaterialRecord(rgb=(63, 224, 63),  use="0",     resistivity_ohm_cm=9.71, er=1, tan_delta=0, mu_r=1, name="steel"),
    MaterialRecord(rgb=(63, 63, 224),  use="-1",    resistivity_ohm_cm=9.71, er=1, tan_delta=0, mu_r=1, name="steel"),
    MaterialRecord(rgb=(63, 224, 224), use="float", resistivity_ohm_cm=9.71, er=1, tan_delta=0, mu_r=1, name="steel"),

    # Tin variants
    MaterialRecord(rgb=(224, 0, 63),   use="+1",    resistivity_ohm_cm=11.4, er=1, tan_delta=0, mu_r=1, name="tin"),
    MaterialRecord(rgb=(0, 224, 63),   use="0",     resistivity_ohm_cm=11.4, er=1, tan_delta=0, mu_r=1, name="tin"),
    MaterialRecord(rgb=(0, 63, 224),   use="-1",    resistivity_ohm_cm=11.4, er=1, tan_delta=0, mu_r=1, name="tin"),
    MaterialRecord(rgb=(0, 255, 224),  use="float", resistivity_ohm_cm=11.4, er=1, tan_delta=0, mu_r=1, name="tin"),

    # 60/40 PbSn solder variants
    MaterialRecord(rgb=(24, 63, 0),    use="+1",    resistivity_ohm_cm=14.5, er=1, tan_delta=0, mu_r=1, name="60/40 PbSn solder"),
    MaterialRecord(rgb=(63, 224, 0),   use="0",     resistivity_ohm_cm=14.5, er=1, tan_delta=0, mu_r=1, name="60/40 PbSn solder"),
    MaterialRecord(rgb=(63, 0, 224),   use="-1",    resistivity_ohm_cm=14.5, er=1, tan_delta=0, mu_r=1, name="60/40 PbSn solder"),
    MaterialRecord(rgb=(63, 255, 224), use="float", resistivity_ohm_cm=14.5, er=1, tan_delta=0, mu_r=1, name="60/40 PbSn solder"),

    # Insulators / dielectrics
    MaterialRecord(rgb=(0, 0, 0),       use="insul", resistivity_ohm_cm=1e6, er=1.0,    tan_delta=0,       mu_r=1, name="vacuum"),
    MaterialRecord(rgb=(255, 255, 255), use="insul", resistivity_ohm_cm=1e6, er=1.0,    tan_delta=0,       mu_r=1, name="vacuum"),
    MaterialRecord(rgb=(255, 202, 202), use="insul", resistivity_ohm_cm=1e6, er=1.0006, tan_delta=0,       mu_r=1, name="air"),
    MaterialRecord(rgb=(130, 53, 239),  use="insul", resistivity_ohm_cm=1e6, er=2.07,   tan_delta=0.00020, mu_r=1, name="teflon"),
    MaterialRecord(rgb=(255, 0, 255),   use="insul", resistivity_ohm_cm=1e6, er=2.26,   tan_delta=0.00064, mu_r=1, name="polyethylene"),
    MaterialRecord(rgb=(255, 255, 0),   use="insul", resistivity_ohm_cm=1e6, er=2.5,    tan_delta=0.00033, mu_r=1, name="polystyrene"),
    MaterialRecord(rgb=(239, 204, 26),  use="insul", resistivity_ohm_cm=1e6, er=4.5,    tan_delta=0.011,   mu_r=1, name="polyvinylchloride"),
    MaterialRecord(rgb=(188, 127, 96),  use="insul", resistivity_ohm_cm=1e6, er=3.335,  tan_delta=0.03,    mu_r=1, name="epoxy resin"),
    MaterialRecord(rgb=(26, 239, 179),  use="insul", resistivity_ohm_cm=1e6, er=4.8,    tan_delta=0.018,   mu_r=1, name="fiberglass/epoxy PCB"),
    MaterialRecord(rgb=(223, 247, 136), use="insul", resistivity_ohm_cm=1e6, er=3.7,    tan_delta=0.018,   mu_r=1, name="FR4 PCB"),
    MaterialRecord(rgb=(142, 142, 142), use="insul", resistivity_ohm_cm=1e6, er=2.2,    tan_delta=0.00090, mu_r=1, name="duroid 5880"),
    MaterialRecord(rgb=(105, 105, 105), use="insul", resistivity_ohm_cm=1e6, er=6.15,   tan_delta=0.00270, mu_r=1, name="duroid 6006"),
    MaterialRecord(rgb=(220, 220, 220), use="insul", resistivity_ohm_cm=1e6, er=10.2,   tan_delta=0.00230, mu_r=1, name="duroid 6010"),
    MaterialRecord(rgb=(213, 160, 77),  use="insul", resistivity_ohm_cm=1e6, er=100.0,  tan_delta=0,       mu_r=1, name="Er=100"),
    MaterialRecord(rgb=(100, 200, 255), use="insul", resistivity_ohm_cm=1e6, er=75.0,   tan_delta=0.157,   mu_r=1, name="distilled water"),
    MaterialRecord(rgb=(176, 224, 200), use="insul", resistivity_ohm_cm=1e6, er=3.78,   tan_delta=0.00006, mu_r=1, name="quartz"),
    MaterialRecord(rgb=(153, 255, 153), use="insul", resistivity_ohm_cm=1e6, er=5.0,    tan_delta=0.00540, mu_r=1, name="glass (varies a lot)"),
)
# fmt: on


def list_atlc2_default() -> list[MaterialRecord]:
    """Return the full atlc2 default material database as a list."""
    return list(ATLC2_DEFAULTS)


def lookup_by_rgb(
    rgb: tuple[int, int, int],
    extra: list[MaterialRecord] | None = None,
) -> MaterialRecord | None:
    """Look up a material by exact RGB triple.

    Search order: ``extra`` (user-defined materials, e.g. from MoreColors.txt) first,
    then the atlc2 default table. Returns None if not found.
    """
    if extra is not None:
        for m in extra:
            if m.rgb == rgb:
                return m
    for m in ATLC2_DEFAULTS:
        if m.rgb == rgb:
            return m
    return None


def find_by_name(name: str) -> list[MaterialRecord]:
    """Return all materials whose name contains ``name`` (case-insensitive)."""
    needle = name.lower()
    return [m for m in ATLC2_DEFAULTS if needle in m.name.lower()]


__all__ = [
    "ATLC2_DEFAULTS",
    "MaterialRecord",
    "MaterialUse",
    "find_by_name",
    "list_atlc2_default",
    "lookup_by_rgb",
]
