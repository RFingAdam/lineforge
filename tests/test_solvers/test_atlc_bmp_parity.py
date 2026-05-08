"""On-disk atlc-format BMP fixtures → bitmap solver parity check.

Locks in three things at once:

1. ``Usermap.from_bmp`` correctly decodes BMP24 files.
2. The atlc2 color-palette lookup feeds the right material to each pixel.
3. The bitmap C/Gp solver agrees with the analytical Z₀ for a known geometry
   to within ±10 % (the parity tolerance documented in AUDIT.md).

The fixtures are regenerable via ``tests/fixtures/usermaps/_generate.py``
to keep their licensing identical to atlc3 itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlc3.geometry.usermap import Usermap
from atlc3.solvers.cgp import solve_cgp

FIXTURES = Path(__file__).parent.parent / "fixtures" / "usermaps"


@pytest.mark.parametrize(
    ("bmp_filename", "expected_z0", "tolerance"),
    [
        ("air_coax_50ohm.bmp", 49.94, 0.10),  # ±10% per AUDIT
        ("air_coax_75ohm.bmp", 75.01, 0.10),
    ],
)
def test_bmp_loads_and_solves_within_tolerance(
    bmp_filename: str, expected_z0: float, tolerance: float
) -> None:
    """Each canonical BMP must load, solve, and produce Z₀ within tolerance."""
    bmp_path = FIXTURES / bmp_filename
    assert bmp_path.exists(), (
        f"missing fixture {bmp_path}; regenerate with "
        f"`python tests/fixtures/usermaps/_generate.py`"
    )

    # Pixel size: read it from the in-memory builder so we always agree.
    from tests.fixtures.geometries import air_coax_50ohm, air_coax_75ohm

    ref_lookup = {
        "air_coax_50ohm.bmp": air_coax_50ohm(),
        "air_coax_75ohm.bmp": air_coax_75ohm(),
    }
    ref = ref_lookup[bmp_filename]
    pixel_width = ref.builder().meta.pixel_width_m

    usermap = Usermap.from_bmp(bmp_path, pixel_width=pixel_width)
    assert usermap.rgb.ndim == 3
    assert usermap.rgb.shape[2] == 3
    assert usermap.meta.pixel_width_m == pytest.approx(pixel_width, rel=1e-9)

    # extend_grid=False because the fixtures are coax — fully shielded by the
    # outer ground; the field is already contained within the bitmap.
    cgp = solve_cgp(usermap, method="sor", tol=1e-5, max_iter=5000, extend_grid=False)
    assert cgp.z0 == pytest.approx(expected_z0, rel=tolerance), (
        f"{bmp_filename}: Z₀ = {cgp.z0:.3f} Ω; "
        f"expected {expected_z0:.3f} Ω ±{tolerance * 100:.0f}%"
    )


def test_bmp_palette_recognized() -> None:
    """The standard atlc2 palette (red signal, green ground, black vacuum)
    must be recognized by the default material lookup — i.e. no pixel is
    rejected as 'unknown color'."""
    bmp_path = FIXTURES / "air_coax_50ohm.bmp"
    usermap = Usermap.from_bmp(bmp_path, pixel_width=12.5e-6)
    # Sample a few pixels and verify each maps to a MaterialRecord.
    h, w = usermap.rgb.shape[:2]
    sampled_pixels = [
        (0, 0),  # corner — likely ground
        (h // 2, w // 2),  # center — likely signal
        (h // 4, w // 4),  # off-center — likely vacuum
    ]
    for y, x in sampled_pixels:
        color = tuple(int(c) for c in usermap.rgb[y, x])
        material = usermap.material_lookup.get(color)
        assert (
            material is not None
        ), f"BMP fixture pixel ({y},{x}) has color {color} not found in palette"


def test_round_trip_via_to_bmp_from_bmp(tmp_path: Path) -> None:
    """Save a known usermap to BMP, load it back, verify pixel-perfect equality."""
    from tests.fixtures.geometries import air_coax_50ohm

    original = air_coax_50ohm().builder()
    out_bmp = tmp_path / "round_trip.bmp"
    original.to_bmp(out_bmp)

    reloaded = Usermap.from_bmp(out_bmp, pixel_width=original.meta.pixel_width_m)
    assert (reloaded.rgb == original.rgb).all()
    assert reloaded.meta.pixel_width_m == pytest.approx(original.meta.pixel_width_m, rel=1e-9)


def test_fixture_regeneration_is_byte_stable() -> None:
    """The committed fixture must equal what _generate.py would produce now.

    If this fails after a builder change in tests/fixtures/geometries.py,
    re-run `python tests/fixtures/usermaps/_generate.py` and commit the new
    BMPs alongside the change.
    """
    from tests.fixtures.geometries import air_coax_50ohm

    ref = air_coax_50ohm()
    fresh_usermap = ref.builder()
    committed = Usermap.from_bmp(
        FIXTURES / "air_coax_50ohm.bmp",
        pixel_width=fresh_usermap.meta.pixel_width_m,
    )
    assert (fresh_usermap.rgb == committed.rgb).all()
