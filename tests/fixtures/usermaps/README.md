# Reference BMP fixtures for parity tests

These are atlc-format BMP24 files used to lock in lineforge's BMP I/O and bitmap
solver against analytically-known transmission lines.

The files are **regenerated locally** (not pulled from the atlc/atlc2
SourceForge tree) so the licensing stays clean. They're MIT, same as the
project. Each BMP uses the standard atlc2 color palette
(red=signal, green=ground, black=vacuum) and a documented pixel size, so the
files are still loadable by atlc/atlc2 themselves and produce the same C
to within their respective solver tolerances.

## Files

| File | Geometry | Z₀ (analytical) | Pixel size |
|---|---|---|---|
| `air_coax_50ohm.bmp` | Air coax a=0.5mm, b=1.15mm | 49.94 Ω | 12.5 µm |
| `air_coax_75ohm.bmp` | Air coax a=0.5mm, b=1.747mm | 75.01 Ω | 18.0 µm |

## Regeneration

If a test fixture is corrupted or you want to regenerate at higher resolution:

```bash
python tests/fixtures/usermaps/_generate.py
```

The script is idempotent (overwrites in place). It uses the same builders
that `tests/fixtures/geometries.py` uses for in-memory parity tests. These
files are simply the on-disk BMP serialization of those geometries.

## Why on-disk fixtures vs in-memory builders

`tests/test_solvers/test_parity.py` already validates the bitmap solver
against analytical references via in-memory `Usermap` objects. The BMP
fixtures additionally exercise:

1. The on-disk BMP file format (atlc/atlc2 compatibility).
2. `Usermap.from_bmp` round-trip (file → numpy → solver).
3. The atlc2 color-palette → MaterialRecord lookup pipeline.

So if a future change to the BMP loader, palette, or material database
silently breaks atlc compatibility, these tests will catch it.
