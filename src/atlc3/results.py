"""Result types returned by atlc3 solvers.

All result models are Pydantic v2 — they serialize to JSON for the MCP surface
and CLI ``--output json``, and have generated JSON Schemas the MCP server uses
to advertise tool return shapes.

Phase 0 ships :class:`TLineResult` (single-line) and :class:`DiffResult`
(differential pair). Phase 3 adds :class:`RLGCResult` with the full
frequency-dependent characterization.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SolverWarning(BaseModel):
    """A non-fatal warning attached to a result.

    Examples: ``Rs_low_confidence`` when conductors are too close (atlc2's
    red-text condition), ``out_of_range`` when an analytical formula's
    validity bounds are exceeded.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="Stable machine-readable warning code.")
    message: str = Field(..., description="Human-readable explanation.")
    severity: Literal["info", "warning", "error"] = "warning"


class TLineResult(BaseModel):
    """Result of a single-mode transmission-line solve.

    Phase 1 (analytical) populates the impedance and dielectric fields. Phase 2
    (C and Gp) adds C, Gp, and a refined vp. Phase 3 (L and Rs) populates the
    full RLGC fields, at which point :class:`RLGCResult` is the preferred
    return type.
    """

    model_config = ConfigDict(extra="forbid")

    # --- impedance / propagation ---------------------------------------------
    z0: float = Field(..., description="Characteristic impedance Z0 [Ω].", gt=0)
    eps_eff: float = Field(..., description="Effective relative permittivity εeff [-].", ge=1)
    vp: float = Field(..., description="Phase velocity [m/s].", gt=0)
    td_per_inch: float = Field(..., description="Propagation delay [s/inch].", gt=0)

    # --- distributed RLGC (filled in by later phases) ------------------------
    L_per_m: float | None = Field(
        None, description="Series inductance per meter [H/m]. Populated by Phase 2/3.", gt=0
    )
    C_per_m: float | None = Field(
        None, description="Shunt capacitance per meter [F/m]. Populated by Phase 2.", gt=0
    )
    Rs_per_m: float | None = Field(
        None, description="Series resistance per meter [Ω/m]. Populated by Phase 3.", ge=0
    )
    Gp_per_m: float | None = Field(
        None, description="Shunt conductance per meter [S/m]. Populated by Phase 2.", ge=0
    )

    # --- loss estimates -------------------------------------------------------
    conductor_loss_db_per_in: float | None = Field(
        None, description="Conductor loss [dB/inch]. Phase 1 estimate; Phase 3 exact.", ge=0
    )
    dielectric_loss_db_per_in: float | None = Field(
        None, description="Dielectric loss [dB/inch]. Phase 1 estimate; Phase 2 exact.", ge=0
    )

    # --- metadata -------------------------------------------------------------
    method: str = Field(..., description="Which solver produced this result.")
    frequency_hz: float | None = Field(
        None, description="Solve frequency [Hz]. None for frequency-independent analytical.", gt=0
    )
    warnings: list[SolverWarning] = Field(default_factory=list)


class DiffResult(BaseModel):
    """Result of a differential-pair solve."""

    model_config = ConfigDict(extra="forbid")

    z_odd: float = Field(..., description="Odd-mode characteristic impedance [Ω].", gt=0)
    z_even: float = Field(..., description="Even-mode characteristic impedance [Ω].", gt=0)
    z_diff: float = Field(..., description="Differential impedance Zdiff = 2·Zodd [Ω].", gt=0)
    z_common: float = Field(..., description="Common-mode impedance Zcommon = Zeven/2 [Ω].", gt=0)
    eps_eff_odd: float = Field(..., description="εeff for the odd mode.", ge=1)
    eps_eff_even: float = Field(..., description="εeff for the even mode.", ge=1)
    vp_odd: float = Field(..., description="Odd-mode phase velocity [m/s].", gt=0)
    vp_even: float = Field(..., description="Even-mode phase velocity [m/s].", gt=0)

    method: str = Field(..., description="Which solver produced this result.")
    frequency_hz: float | None = Field(None, gt=0)
    warnings: list[SolverWarning] = Field(default_factory=list)


class ThreeWireResult(BaseModel):
    """Result of a 3-conductor (Y-decomposed) line analysis.

    Per ``docs/theory/three_wire.md``, a 3-wire line has no single Z₀ — three
    pair-wise impedances combine in a "Y" arrangement. We carry both the raw
    pair impedances (each with one conductor floating) and the derived Y-leg
    impedances + odd/even mode equivalents.

    Attributes
    ----------
    z_rcz, z_gcz, z_bcz
        Pair impedances (red+green active, etc.); the suffix names which
        conductor is set to current-zero (floating).
    zo_r, zo_g, zo_b
        Y-decomposition: each is the impedance of one Y leg. Computed via
        ``zo_r = (z_gcz + z_bcz − z_rcz) / 2`` and analogous.
    z_odd, z_even
        Coupler odd/even mode impedances when the geometry is interpreted as
        a directional coupler (red + blue as the two signal lines, green as
        ground).
    ignd_ratio
        |I_ground / I_signal| ratio. If > 0.04 the line is radiating and the
        Z₀ values are not true characteristic impedances (atlc2 4 % red-text
        warning); a SolverWarning with code ``radiating_3wire`` is appended
        in that case.
    """

    model_config = ConfigDict(extra="forbid")

    z_rcz: float = Field(..., description="Pair Z₀ with red current-zero (R floating).", gt=0)
    z_gcz: float = Field(..., description="Pair Z₀ with green current-zero (G floating).", gt=0)
    z_bcz: float = Field(..., description="Pair Z₀ with blue current-zero (B floating).", gt=0)

    zo_r: float = Field(..., description="Y-leg impedance for the red (+1) conductor.")
    zo_g: float = Field(..., description="Y-leg impedance for the green (0) conductor.")
    zo_b: float = Field(..., description="Y-leg impedance for the blue (−1) conductor.")

    z_odd: float = Field(..., description="Coupler odd-mode impedance.", gt=0)
    z_even: float = Field(..., description="Coupler even-mode impedance.", gt=0)

    ignd_ratio: float = Field(
        0.0,
        description="|Iground/Isignal| ratio (radiation indicator).",
        ge=0,
    )

    method: str = Field(..., description="Which solver produced this result.")
    frequency_hz: float | None = Field(None, gt=0)
    warnings: list[SolverWarning] = Field(default_factory=list)


__all__ = ["DiffResult", "SolverWarning", "TLineResult", "ThreeWireResult"]
