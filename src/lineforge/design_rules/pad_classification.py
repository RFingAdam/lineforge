"""Pad classification. When to follow reference design vs when to optimize.

For any RF pad on a PCB, the design decision (relieve GND under it?
shrink it? leave it alone?) depends on **whose RF certification or
matching network is in play**, not on the pad's electrical numbers
alone. This module formalizes that decision into three categories.

Category 1: Follow the reference design
    The pad is part of a certified RF subsystem (FCC modular grant) or
    a manufacturer-spec'd connector whose 50 Ω behavior depends on the
    reference land pattern. Deviating risks:
      - Regulatory invalidation (modular grant doesn't transfer)
      - IC matching network detune (the IC's internal LC assumes the
        reference pad capacitance)
      - Connector launch mistune (the connector itself is the 50 Ω
        structure, tuned for the reference pad)

Category 2: Optimize freely
    The pad is in your own RF circuit (passive filter, your matching
    network, antenna feed). You define the impedance environment. No
    upstream cert or matching network in play. Use
    :func:`lineforge.analytical.pads.pad_relief_advisor` to pick the
    minimum-invasive relief that meets your RL target.

Category 3: Standard practice
    The pad is non-RF or low-RF (DC, power, low-speed signal). No RF
    performance constraint. Use solid GND for thermal balance and EMC
    containment.

The classifier takes pad context (what it's connected to) and returns
the category plus specific guidance text suitable for design notes or
agent reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PadCategory(StrEnum):
    """Three categories of RF pad design treatment."""

    FOLLOW_REFERENCE = "Category 1: Follow reference design"
    """Pad is in a certified module or spec'd connector path. Don't
    deviate from the manufacturer's documented land pattern."""

    OPTIMIZE = "Category 2: Optimize freely"
    """Pad is in your own RF circuit. Apply relief / sizing optimization
    per your RL budget."""

    STANDARD = "Category 3: Standard practice"
    """Pad is non-RF / low-RF. Use standard solid-GND layout for
    thermal and EMC reasons."""


@dataclass
class PadClassification:
    """Result of classifying a pad."""

    category: PadCategory
    """Which of the three categories applies."""

    guidance: list[str]
    """Concrete design actions to take for this pad."""

    risks_if_deviating: list[str]
    """What goes wrong if you do the wrong thing (informational)."""

    references: list[str]
    """Links/citations the engineer should consult (datasheet sections,
    FCC rules, IC manufacturer integration guides, etc.)."""


def classify_pad(
    *,
    component_type: str,
    has_modular_grant: bool = False,
    is_user_designed_rf: bool = False,
    operating_freq_ghz: float | None = None,
) -> PadClassification:
    """Classify a pad into Category 1, 2, or 3.

    Parameters
    ----------
    component_type
        What the pad serves. Free-form string; common values:
        ``"wifi_module"``, ``"lte_module"``, ``"ble_module"``,
        ``"rf_connector"``, ``"u.fl"``, ``"sma"``, ``"mmcx"``,
        ``"triplexer"``, ``"diplexer"``, ``"discrete_lc"``, ``"saw"``,
        ``"baw"``, ``"lna"``, ``"mixer"``, ``"pa"``, ``"dc_block"``,
        ``"decoupling"``, ``"power"``, ``"ground"``, ``"low_speed_io"``.
    has_modular_grant
        True if the component carries its own FCC/CE modular approval
        that would transfer to your product (typical for finished Wi-Fi
        and cellular modules).
    is_user_designed_rf
        True if this is a passive component you specified (no
        manufacturer-tuned matching network internally: just a part
        with documented characteristic impedance).
    operating_freq_ghz
        Highest operating frequency on this pad. Used to flag low-speed
        pads (< 100 MHz) as Category 3 automatically.

    Returns
    -------
    PadClassification
        Category + specific guidance for design / review notes.

    Examples
    --------
    >>> r = classify_pad(component_type="wifi_module", has_modular_grant=True)
    >>> r.category
    <PadCategory.FOLLOW_REFERENCE: 'Category 1: Follow reference design'>

    >>> r = classify_pad(component_type="triplexer", is_user_designed_rf=True)
    >>> r.category
    <PadCategory.OPTIMIZE: 'Category 2: Optimize freely'>
    """
    ct = component_type.lower().strip()

    # Low-speed / DC pads → Category 3 regardless
    if operating_freq_ghz is not None and operating_freq_ghz < 0.1:
        return PadClassification(
            category=PadCategory.STANDARD,
            guidance=[
                "Use standard PCB practice: solid GND under pad for thermal balance.",
                "No RF relief needed below ~100 MHz operation.",
            ],
            risks_if_deviating=[],
            references=[],
        )
    if ct in {"power", "ground", "dc", "low_speed_io", "thermal_pad"}:
        return PadClassification(
            category=PadCategory.STANDARD,
            guidance=[
                "Standard PCB practice: solid GND / power-plane connection.",
                "Maximize thermal mass coupling to internal copper.",
            ],
            risks_if_deviating=[
                "Reducing copper under thermal pads degrades component lifetime.",
            ],
            references=[],
        )

    # Module pads with modular grant → Category 1
    module_kinds = {
        "wifi_module",
        "lte_module",
        "ble_module",
        "cellular_module",
        "5g_module",
        "lora_module",
        "bt_module",
        "uwb_module",
    }
    if ct in module_kinds or has_modular_grant:
        return PadClassification(
            category=PadCategory.FOLLOW_REFERENCE,
            guidance=[
                "Follow the module manufacturer's reference layout exactly.",
                "Match pad geometry, GND configuration, and stitching via "
                "pattern in the integration guide.",
                "Do NOT add ground relief unilaterally: module's internal "
                "matching network assumes the reference pad capacitance.",
                "If you observe high VSWR at the antenna port, contact the "
                "FAE before deviating; alternative reference layouts may exist.",
            ],
            risks_if_deviating=[
                "Modular FCC grant may not transfer to your host: full "
                "intentional-radiator testing becomes required.",
                "Module's internal LC match detunes; TX power and RX " "sensitivity degrade.",
                "Vendor support / warranty claims may be voided.",
            ],
            references=[
                "Module datasheet: 'Integration Guide' or 'PCB Layout' section",
                "FCC Part 15.247(c)(3): Limited Modular Approval transfer rules",
                "Module manufacturer FAE for layout deviations",
            ],
        )

    # RF connectors → Category 1 (the connector IS the 50 Ω structure)
    connector_kinds = {
        "u.fl",
        "ufl",
        "u_fl",
        "w.fl",
        "wfl",
        "mmcx",
        "sma",
        "rp-sma",
        "rpsma",
        "mcx",
        "smp",
        "smpm",
        "smpc",
        "n_type",
        "bnc",
        "tnc",
        "rf_connector",
        "rf_jack",
    }
    if ct in connector_kinds:
        return PadClassification(
            category=PadCategory.FOLLOW_REFERENCE,
            guidance=[
                "Follow the connector manufacturer's recommended land pattern.",
                "The connector + reference pad together form the 50 Ω "
                "transition. Don't relieve the signal pad.",
                "If high-frequency performance is critical, consider a "
                "higher-band connector variant rather than modifying the pad.",
                "Verify mechanical fitment: GND pads support the connector "
                "during reflow and mating cycles.",
            ],
            risks_if_deviating=[
                "Connector's 50 Ω characterization no longer applies.",
                "Mechanical retention compromised: connector can crack or "
                "lift after mating cycles.",
                "VSWR mismatch with the connector that no amount of trace " "tuning can recover.",
            ],
            references=[
                "Connector datasheet: 'Recommended PCB Land Pattern' section",
                "Manufacturer application note on host-board integration",
            ],
        )

    # User-designed RF circuit → Category 2
    user_rf_kinds = {
        "triplexer",
        "diplexer",
        "duplexer",
        "discrete_lc",
        "matching_component",
        "matching_network",
        "antenna_feed",
        "antenna",
        "filter",
        "saw_filter",
        "baw_filter",
        "balun",
        "coupler",
        "splitter",
    }
    if ct in user_rf_kinds or is_user_designed_rf:
        return PadClassification(
            category=PadCategory.OPTIMIZE,
            guidance=[
                "Optimize freely. No external matching/grant constraints.",
                "Run pad_relief_advisor() against your RL budget and the "
                "highest operating frequency.",
                "Pick the minimum-invasive relief that meets the target "
                "(typically: shrink pad first, then relieve underneath).",
                "Coordinate with the via-transition design if the pad has "
                "a via going to an inner layer.",
            ],
            risks_if_deviating=[],
            references=[
                "lineforge.analytical.pads.pad_relief_advisor() for option ranking",
                "IPC-2141A on RF transmission-line design",
            ],
        )

    # Other RF ICs (LNA, mixer, PA). Check datasheet, usually Category 1
    other_rf_ic_kinds = {"lna", "mixer", "pa", "vco", "synthesizer", "rf_ic", "rfic", "transceiver"}
    if ct in other_rf_ic_kinds:
        return PadClassification(
            category=PadCategory.FOLLOW_REFERENCE,
            guidance=[
                "Check the IC datasheet's recommended PCB layout.",
                "Most RF ICs assume a specific pad geometry for their "
                "internal matching network: follow it.",
                "If the datasheet is silent on layout, treat as Category 2 "
                "and optimize per the application.",
            ],
            risks_if_deviating=[
                "Detuned internal matching causes input/output VSWR mismatch.",
                "Manufacturer support may not apply to non-reference layouts.",
            ],
            references=[
                "IC datasheet: 'Application Information' or 'Layout' section",
                "Manufacturer application note for the part family",
            ],
        )

    # Fallback: ambiguous → recommend caution
    return PadClassification(
        category=PadCategory.FOLLOW_REFERENCE,
        guidance=[
            f"Component type {component_type!r} is ambiguous: defaulting to "
            "Category 1 (follow reference design) as the safe choice.",
            "If this is your own RF circuit with no upstream matching/cert "
            "constraints, pass is_user_designed_rf=True to get Category 2.",
        ],
        risks_if_deviating=[
            "Unknown: depends on the actual component.",
        ],
        references=[
            "Check component datasheet for layout guidance.",
        ],
    )


__all__ = ["PadCategory", "PadClassification", "classify_pad"]
