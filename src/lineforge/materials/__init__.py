"""Material database: atlc2's 45 standard colors plus extensions.

Phase 1 ships the static atlc2 default table accessible via :func:`list_atlc2_default`.
Phase 2 adds:
- :func:`parse_morecolors_text` / :func:`parse_morecolors_file` for atlc2 ``MoreColors.txt`` compat.
- :func:`load_json_pack` / :func:`dump_json_pack` for the lineforge-native JSON format.
- :func:`build_lookup` to compose user packs on top of the atlc2 defaults.
"""

from __future__ import annotations

from lineforge.materials.database import (
    ATLC2_DEFAULTS,
    MaterialRecord,
    MaterialUse,
    find_by_name,
    list_atlc2_default,
    lookup_by_rgb,
)
from lineforge.materials.morecolors import (
    MoreColorsParseError,
    dedupe_keep_last,
    dump_json_pack,
    load_json_pack,
    parse_morecolors_file,
    parse_morecolors_text,
    to_morecolors_text,
)


def build_lookup(
    user_packs: list[list[MaterialRecord]] | None = None,
) -> dict[tuple[int, int, int], MaterialRecord]:
    """Build an RGB→material lookup table.

    The atlc2 defaults populate the base. ``user_packs`` are overlaid in order;
    later packs override earlier ones if RGB values collide (matches atlc2's
    last-wins MoreColors.txt semantics).
    """
    table: dict[tuple[int, int, int], MaterialRecord] = {m.rgb: m for m in ATLC2_DEFAULTS}
    for pack in user_packs or []:
        for m in pack:
            table[m.rgb] = m
    return table


__all__ = [
    "ATLC2_DEFAULTS",
    "MaterialRecord",
    "MaterialUse",
    "MoreColorsParseError",
    "build_lookup",
    "dedupe_keep_last",
    "dump_json_pack",
    "find_by_name",
    "list_atlc2_default",
    "load_json_pack",
    "lookup_by_rgb",
    "parse_morecolors_file",
    "parse_morecolors_text",
    "to_morecolors_text",
]
