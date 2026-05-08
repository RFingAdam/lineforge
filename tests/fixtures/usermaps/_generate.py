"""Regenerate the on-disk BMP fixtures from the in-memory builders.

Run when adding a new fixture or fixing a corrupted file:

    python tests/fixtures/usermaps/_generate.py

The script is idempotent — it overwrites in place — and is checked into the
repo so anyone can reproduce the fixtures byte-for-byte.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project's tests directory importable.
_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from tests.fixtures.geometries import (  # noqa: E402  (sys.path manipulation above)
    air_coax_50ohm,
    air_coax_75ohm,
)


def main() -> None:
    cases = {
        "air_coax_50ohm.bmp": air_coax_50ohm(),
        "air_coax_75ohm.bmp": air_coax_75ohm(),
    }
    for filename, ref in cases.items():
        usermap = ref.builder()
        out = _HERE / filename
        usermap.to_bmp(out)
        print(f"wrote {out.relative_to(_ROOT)} ({usermap.rgb.shape[1]}×{usermap.rgb.shape[0]} px)")


if __name__ == "__main__":
    main()
