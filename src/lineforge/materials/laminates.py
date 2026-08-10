"""Laminate lookup with fuzzy name matching and frequency interpolation.

lineforge ships a curated library of PCB laminates (FR4 family, low-loss
hydrocarbons, ceramics) in ``materials/packs/pcb_extended.json``. This
module exposes a single ergonomic entry point :func:`laminate_lookup`
that resolves either an exact or fuzzy-matched name plus an operating
frequency to ``(εr, Df)``.

Examples
--------
>>> r = laminate_lookup("FR4 prepreg", frequency_ghz=2.4)
>>> round(r.er, 2), round(r.tan_delta, 3)
(3.7, 0.018)

>>> r = laminate_lookup("Isola 370HR")
>>> r.name
'Isola 370HR'

The fuzzy match handles common shorthand:

- "FR4", "FR-4", "fr4 nominal"          → FR4 nominal (er=4.4)
- "FR4 core", "fr4-core"                → FR4 Core (er=4.2)
- "FR4 prepreg", "FR-4 prepreg"         → FR4 Prepreg (er=3.7)
- "RO4350", "Rogers 4350", "RO4350B"    → Rogers RO4350B
- "Megtron 6", "M6"                     → Megtron 6 (Panasonic R-5775)
- "ITEQ 180", "IT-180A"                 → ITEQ IT-180A
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any, cast

from lineforge.materials.dispersion import material_at_frequency


@dataclass
class LaminateResult:
    """Result of a laminate lookup."""

    name: str
    """Canonical laminate name from the database."""

    er: float
    """Relative permittivity at the requested frequency."""

    tan_delta: float
    """Loss tangent (Df) at the requested frequency."""

    frequency_ghz: float | None
    """The frequency the lookup was resolved at (None for nominal/no-freq)."""

    matched_by: str
    """How the lookup found the entry: ``"exact"``, ``"alias"``, or
    ``"fuzzy"`` (substring/token match)."""


# Aliases that map various shorthand to canonical names.
_ALIASES: dict[str, str] = {
    "fr4": "FR4 nominal (er=4.4)",
    "fr-4": "FR4 nominal (er=4.4)",
    "fr4 nominal": "FR4 nominal (er=4.4)",
    "fr4 core": "FR4 Core (er=4.2)",
    "fr-4 core": "FR4 Core (er=4.2)",
    "fr4-core": "FR4 Core (er=4.2)",
    "fr4 prepreg": "FR4 Prepreg (er=3.7)",
    "fr-4 prepreg": "FR4 Prepreg (er=3.7)",
    "fr4-prepreg": "FR4 Prepreg (er=3.7)",
    "ro4350": "Rogers RO4350B",
    "ro4350b": "Rogers RO4350B",
    "rogers 4350": "Rogers RO4350B",
    "rogers 4350b": "Rogers RO4350B",
    "ro4003": "Rogers RO4003C",
    "ro4003c": "Rogers RO4003C",
    "ro3003": "Rogers RO3003",
    "ro3006": "Rogers RO3006",
    "ro3010": "Rogers RO3010",
    "megtron 4": "Megtron 4 (Panasonic R-5725)",
    "megtron 6": "Megtron 6 (Panasonic R-5775)",
    "megtron 7": "Megtron 7-N (Panasonic R-5785N)",
    "megtron 7-n": "Megtron 7-N (Panasonic R-5785N)",
    "m4": "Megtron 4 (Panasonic R-5725)",
    "m6": "Megtron 6 (Panasonic R-5775)",
    "m7": "Megtron 7-N (Panasonic R-5785N)",
    "370hr": "Isola 370HR",
    "isola 370hr": "Isola 370HR",
    "i-tera mt40": "Isola I-Tera MT40",
    "i-tera": "Isola I-Tera MT40",
    "tachyon 100g": "Isola Tachyon 100G",
    "tachyon": "Isola Tachyon 100G",
    "tachyon-100g": "Isola Tachyon 100G",
    "iteq 150da": "ITEQ IT-150DA",
    "iteq it-150da": "ITEQ IT-150DA",
    "it-150da": "ITEQ IT-150DA",
    "iteq 180a": "ITEQ IT-180A",
    "iteq it-180a": "ITEQ IT-180A",
    "it-180a": "ITEQ IT-180A",
    "kapton": "polyimide (Kapton)",
    "polyimide": "polyimide (Kapton)",
    "alumina": "alumina (Al2O3, 99%)",
    "al2o3": "alumina (Al2O3, 99%)",
}


def _load_pack() -> list[dict[str, Any]]:
    """Load the pcb_extended.json pack as a list of material dicts."""
    pack_path = resources.files("lineforge.materials.packs").joinpath("pcb_extended.json")
    with pack_path.open("r") as f:
        data = cast(dict[str, Any], json.load(f))
    return cast(list[dict[str, Any]], data.get("materials", []))


def _normalize(name: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation for matching."""
    return re.sub(r"\s+", " ", name.strip().lower())


def laminate_lookup(
    name: str,
    *,
    frequency_ghz: float | None = None,
) -> LaminateResult:
    """Look up a laminate by name (with fuzzy matching) at an optional frequency.

    Parameters
    ----------
    name
        Laminate name. Accepts exact canonical names ("Rogers RO4350B"),
        common aliases ("FR4 prepreg", "Megtron 6", "RO4350B"), or fuzzy
        substring matches against any laminate in the database.
    frequency_ghz
        If provided and the laminate has frequency-tabulated εr/Df, the
        values are log-frequency interpolated. If omitted, the constant
        ``er`` / ``tan_delta`` from the database is returned.

    Returns
    -------
    LaminateResult
        Canonical name + εr + Df + matched_by indicator.

    Raises
    ------
    KeyError
        If no laminate matches the given name (exact, alias, or fuzzy).
    """
    materials = _load_pack()
    if not materials:
        raise RuntimeError("lineforge laminate database is empty")

    norm_query = _normalize(name)
    by_name = {m["name"]: m for m in materials}
    norm_to_canonical = {_normalize(m["name"]): m["name"] for m in materials}

    canonical: str | None = None
    matched_by: str = ""

    # 1. Exact match (case-insensitive on canonical name)
    if norm_query in norm_to_canonical:
        canonical = norm_to_canonical[norm_query]
        matched_by = "exact"
    # 2. Alias match
    elif norm_query in _ALIASES:
        canonical = _ALIASES[norm_query]
        matched_by = "alias"
    else:
        # 3. Substring fuzzy match against canonical names
        candidates = [c for nq, c in norm_to_canonical.items() if norm_query in nq]
        if len(candidates) == 1:
            canonical = candidates[0]
            matched_by = "fuzzy"
        elif len(candidates) > 1:
            raise KeyError(
                f"Ambiguous laminate name {name!r} — matches: {sorted(candidates)}. "
                "Use a more specific name."
            )

    if canonical is None or canonical not in by_name:
        raise KeyError(
            f"No laminate named {name!r}. Try one of: "
            + ", ".join(sorted(by_name.keys())[:6])
            + ", ..."
        )

    record = by_name[canonical]
    er_const = float(record["er"])
    tan_const = float(record["tan_delta"])

    # Parse er_freq / tan_freq tables (JSON keys are strings)
    er_freq_raw = record.get("er_freq")
    tan_freq_raw = record.get("tan_freq")

    def _parse_freq_table(raw: dict[str, Any] | None) -> dict[float, float] | None:
        if not raw:
            return None
        return {float(k): float(v) for k, v in raw.items()}

    er_freq = _parse_freq_table(er_freq_raw)
    tan_freq = _parse_freq_table(tan_freq_raw)

    freq_hz = float(frequency_ghz) * 1e9 if frequency_ghz is not None else None
    er, tan_delta = material_at_frequency(
        er=er_const,
        tan_delta=tan_const,
        er_freq=er_freq,
        tan_freq=tan_freq,
        freq_hz=freq_hz,
    )

    return LaminateResult(
        name=canonical,
        er=er,
        tan_delta=tan_delta,
        frequency_ghz=frequency_ghz,
        matched_by=matched_by,
    )


def list_laminates() -> list[str]:
    """Return the list of canonical laminate names in the database."""
    return sorted(m["name"] for m in _load_pack())


__all__ = ["LaminateResult", "laminate_lookup", "list_laminates"]
