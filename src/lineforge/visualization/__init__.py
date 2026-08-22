"""Field visualization: render V/E/D/J/loss fields as PNGs.

Phase 2 ships :func:`render_field` matching atlc2's U/V/E/D/T keyboard modes.
"""

from __future__ import annotations

from lineforge.visualization.fields import render_contour_lines, render_field

__all__ = ["render_contour_lines", "render_field"]
