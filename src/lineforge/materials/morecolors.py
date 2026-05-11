"""Parser for atlc2's ``MoreColors.txt`` user-defined material file.

Format (from atlc2 docs at http://www.hdtvprimer.com/kq6qv/atlc2.html):

    | red:  green:  blue:  use:    Ohms:    Er:    tanDelta:  Mu:  name:
    250    20      20     +1       7.3      1      0          1    Cadmium
    30     255     30     0        20.6     1      0          1    Lead
    180    180     120    insul    0        6.0    0.0007     1    Mica

Rules (from atlc2 docs):
- Whitespace-delimited; consecutive blanks treated as one; tabs treated as blanks.
- ``|`` starts a line comment; the rest of the line is ignored.
- Blank lines are allowed.
- The material name field captures *everything* remaining on the line (may contain spaces).
- Duplicate RGB definitions: last one wins (matches atlc2's behavior).
- ``use`` must be one of ``+1`` / ``-1`` / ``0`` / ``float`` / ``insul``.

We also support the ``.lineforge.json`` material-pack format
(:func:`load_json_pack`) which is roundtrippable with the legacy text form.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lineforge.materials.database import MaterialRecord, MaterialUse


class MoreColorsParseError(ValueError):
    """Raised when a MoreColors.txt file cannot be parsed.

    Includes the offending line number for diagnostics.
    """

    def __init__(self, lineno: int, message: str) -> None:
        super().__init__(f"line {lineno}: {message}")
        self.lineno = lineno


def _strip_comments(line: str) -> str:
    """Remove the ``|`` comment portion of a line."""
    bar = line.find("|")
    return line if bar == -1 else line[:bar]


def _tokenize(line: str) -> list[str]:
    """Split on any whitespace, collapsing consecutive separators (matches atlc2)."""
    return line.split()


def _parse_use(token: str, lineno: int) -> MaterialUse:
    if token in {"+1", "-1", "0", "float", "insul"}:
        return token  # type: ignore[return-value]
    raise MoreColorsParseError(
        lineno, f"unknown 'use' value {token!r}; expected +1/-1/0/float/insul"
    )


def parse_morecolors_text(text: str) -> list[MaterialRecord]:
    """Parse a MoreColors.txt-style block of text into MaterialRecords.

    Parameters
    ----------
    text
        File contents.

    Returns
    -------
    list[MaterialRecord]
        One record per non-comment, non-blank line.

    Raises
    ------
    MoreColorsParseError
        If a line cannot be parsed. The exception includes the line number.

    Notes
    -----
    Duplicate RGB values are *kept* in this output list — duplicate handling
    (last-wins) happens at lookup time in :func:`lookup_by_rgb`. If you want
    deduplication, run the result through :func:`dedupe_keep_last`.
    """
    records: list[MaterialRecord] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        cleaned = _strip_comments(raw).strip()
        if not cleaned:
            continue
        tokens = _tokenize(cleaned)
        if len(tokens) < 8:
            raise MoreColorsParseError(
                lineno,
                f"expected at least 8 fields, got {len(tokens)}: {cleaned!r}",
            )

        try:
            r = int(tokens[0])
            g = int(tokens[1])
            b = int(tokens[2])
        except ValueError as exc:
            raise MoreColorsParseError(lineno, f"invalid RGB integers: {exc}") from exc

        if not all(0 <= ch <= 255 for ch in (r, g, b)):
            raise MoreColorsParseError(lineno, f"RGB values must be in 0–255, got ({r}, {g}, {b})")

        use = _parse_use(tokens[3], lineno)

        try:
            resistivity = float(tokens[4])
            er = float(tokens[5])
            tan_d = float(tokens[6])
            mu_r = float(tokens[7])
        except ValueError as exc:
            raise MoreColorsParseError(lineno, f"invalid numeric field: {exc}") from exc

        # The name reclaims everything after the 8th token, preserving spaces.
        # We can't just .join(tokens[8:]) because that collapses spaces. Instead
        # find the position of the 8th field's end in the cleaned line.
        idx = 0
        for ti in range(8):
            idx = cleaned.find(tokens[ti], idx)
            if idx == -1:
                break
            idx += len(tokens[ti])
        name = cleaned[idx:].strip() if idx >= 0 else " ".join(tokens[8:])
        if not name:
            raise MoreColorsParseError(lineno, "missing material name")

        # For insulators, atlc2 conventionally writes resistivity=0 to mean "ignored";
        # we map that to a large dummy resistivity so MaterialRecord doesn't reject it.
        if use == "insul" and resistivity == 0:
            resistivity = 1e6

        records.append(
            MaterialRecord(
                rgb=(r, g, b),
                use=use,
                resistivity_ohm_cm=resistivity,
                er=er if er >= 1 else 1.0,
                tan_delta=tan_d,
                mu_r=mu_r,
                name=name,
            )
        )
    return records


def parse_morecolors_file(path: str | Path) -> list[MaterialRecord]:
    """Parse a MoreColors.txt file from disk."""
    return parse_morecolors_text(Path(path).read_text())


def dedupe_keep_last(records: list[MaterialRecord]) -> list[MaterialRecord]:
    """Drop earlier entries with duplicate RGB triples (atlc2 last-wins behavior)."""
    seen: dict[tuple[int, int, int], MaterialRecord] = {}
    for r in records:
        seen[r.rgb] = r
    return list(seen.values())


def to_morecolors_text(records: list[MaterialRecord]) -> str:
    """Serialize records back to MoreColors.txt format. Round-trippable."""
    lines = [
        "| red:  green:  blue:  use:    Ohms:    Er:    tanDelta:  Mu:  name:",
    ]
    for r in records:
        red, green, blue = r.rgb
        lines.append(
            f"{red:<5} {green:<5} {blue:<5} "
            f"{r.use:<7} {r.resistivity_ohm_cm:<8} "
            f"{r.er:<7} {r.tan_delta:<10} {r.mu_r:<5} {r.name}"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# JSON pack format (lineforge-native)
# --------------------------------------------------------------------------


def load_json_pack(path: str | Path) -> list[MaterialRecord]:
    """Load a JSON-format material pack.

    Format::

        {
          "name": "my-pack",
          "version": "1.0.0",
          "materials": [
            {"rgb": [250, 20, 20], "use": "+1", "resistivity_ohm_cm": 7.3,
             "er": 1, "tan_delta": 0, "mu_r": 1, "name": "Cadmium"},
            ...
          ]
        }
    """
    blob: dict[str, Any] = json.loads(Path(path).read_text())
    materials = blob.get("materials", [])

    def _to_freq_dict(raw: dict[str, Any] | None) -> dict[float, float] | None:
        """JSON has only string keys; coerce them to float for the {Hz: value} dicts."""
        if not raw:
            return None
        return {float(k): float(v) for k, v in raw.items()}

    return [
        MaterialRecord(
            rgb=tuple(m["rgb"]),
            use=m["use"],
            resistivity_ohm_cm=float(m.get("resistivity_ohm_cm", 1e6)),
            er=float(m.get("er", 1.0)),
            tan_delta=float(m.get("tan_delta", 0.0)),
            mu_r=float(m.get("mu_r", 1.0)),
            name=m["name"],
            er_freq=_to_freq_dict(m.get("er_freq")),
            tan_freq=_to_freq_dict(m.get("tan_freq")),
        )
        for m in materials
    ]


def dump_json_pack(
    records: list[MaterialRecord],
    *,
    name: str = "lineforge-pack",
    version: str = "1.0.0",
) -> str:
    """Serialize records to the JSON-pack format. Returns a JSON string."""
    return json.dumps(
        {
            "name": name,
            "version": version,
            "materials": [m.model_dump(mode="json") for m in records],
        },
        indent=2,
    )


__all__ = [
    "MoreColorsParseError",
    "dedupe_keep_last",
    "dump_json_pack",
    "load_json_pack",
    "parse_morecolors_file",
    "parse_morecolors_text",
    "to_morecolors_text",
]
