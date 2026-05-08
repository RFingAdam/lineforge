# Changelog

All notable changes to atlc3.0 are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] — 2026-05-08

First stable release. atlc3 is now feature-complete vs the Phase 0-4 plan
plus the post-1.0 Phase A work (multi-layer stacks, Touchstone export,
ergonomic optimizer wrapper, expanded laminate library, frequency-dependent
materials, atlc-format BMP parity fixtures, broader test coverage).

### Added since 0.1.0

#### Multi-layer dielectric stack (A1)
- `atlc3.geometry.DielectricLayer` Pydantic model + `series_reduce` helper.
- `StriplineAsymmetric.stack_above` / `stack_below` for stratified
  cross-sections (e.g. Prepreg + voided plane + Core when an intermediate
  plane is voided to push the reference down).
- Capacitance-weighted εr_eq and tan_δ_eq via the parallel-plate / series-cap
  reduction. Method tag becomes
  `ipc2141-stripline-asymmetric-multilayer-stack` when stacks are present.
- Bitmap rasterizer paints each layer with its own synthesized RGB +
  material record, so the bitmap solver sees the actual stratified geometry.

#### Split-εr asymmetric stripline (pre-A1)
- `StriplineAsymmetric.er_above` / `er_below` (and matching tan_δ fields)
  for two-dielectric inner-layer traces (Core above ≠ Prepreg below). The
  closed-form solver uses a capacitance-weighted εr_eff; the rasterizer
  paints two distinct halves with synthesized RGB.

#### Touchstone (.s2p) export (A2)
- `atlc3.touchstone.to_touchstone(sweep_results, path, *, line_length, z_ref)`
  emits a 2-port Touchstone v1 file via scikit-rf.
- CLI: `atlc3 sweep --touchstone-out trace.s2p --line-length 1in --z-ref 50`.
- MCP: `sweep` tool gains `touchstone_out`, `line_length`, `z_ref` params;
  returns the file path under `result.touchstone`.

#### `target_z0` ergonomic wrapper (A3)
- `atlc3.optimize.target_z0(template, *, vary, target_ohms, ...)` —
  one-liner for "what trace width gives me 50 Ω on this stackup?"
- Bundled convergence fix: `optimize_for`'s 1D scalar minimizer now uses
  `xatol` scaled to 1e-9 of the search interval (was scipy's default 1e-5
  in absolute SI, which is huge when bounds are in meters). The L3 SIG1
  benchmark now lands W=3.182 mil and Z₀=48.000 Ω.
- CLI: `atlc3 target-z0 --type microstrip --target 50 --fixed H=4mil,...`
- MCP: `target_z0` tool.

#### Frequency-dependent εr / tan_δ + expanded laminate library (A4)
- `MaterialRecord` gains optional `er_freq` / `tan_freq` mappings
  (`{Hz: value}`); `record.at_frequency(f)` interpolates log-linearly.
- New `atlc3.materials.dispersion` with `interpolate_log_freq` and
  `material_at_frequency` helpers.
- `pcb_extended.json` expanded from 10 → 18 entries: Rogers RO4350B/
  RO4003C/RO3003/RO3010/RO3006, Panasonic Megtron 4/6/7-N (multi-frequency
  Dk/Df), Isola 370HR / I-Tera MT40 / Tachyon 100G, ITEQ IT-150DA/180A,
  plus FR4 Core/Prepreg generics.

#### atlc-format BMP fixtures + parity tests (A5)
- New `tests/fixtures/usermaps/` directory with `air_coax_50ohm.bmp`,
  `air_coax_75ohm.bmp` and a `_generate.py` regen script.
- `tests/test_solvers/test_atlc_bmp_parity.py` exercises BMP I/O round-trip
  + atlc2 palette lookup + bitmap solver against analytical references
  within ±10 % Z₀.

#### Test coverage uplift (A6)
- Coverage 63 % → 70 %.
- New tests for `atlc3.visualization.fields` (0 % → 99 %),
  `atlc3.viewer` (0 % → 100 %), `atlc3.scripting.atlc2_script` (46 % → 71 %).
- Outstanding gaps (cli.py, mcp_server, builders, diff_modes) tracked
  for follow-up; the `--cov-fail-under=90` flag stays held until those
  close.

#### Examples
- `examples/06_dielectric_stack.py` — L3 SIG1 void-L4 stackup walkthrough.
- `examples/07_touchstone_export.py` — sweep + .s2p export + skrf reload.

### Changed
- `optimize_for` 1D scalar minimization tolerance is now scaled to the
  search interval; user-visible side-effect is far tighter convergence on
  Z₀ targets (≤ 1e-9 relative error vs the previous ~1 %).
- `MaterialRecord` is forward-compatible with frequency-tabulated εr / tan_δ
  while remaining backward-compatible: existing constant-only records still
  return the same numbers from `at_frequency()` as their bulk fields.

### Phase 4 — Polish + 1.0.0 prep
- Added geometry optimizer (`atlc3.optimize_for`) — wrap scipy.optimize for
  finding dimensions that hit Z0 / Zdiff / εeff targets.
- Added disk-cached solves (`atlc3.cache`) — repeated runs are instant.
  Disable with `ATLC3_NO_CACHE=1`.
- Theory documentation: Laplace solver, Faraday solver, skin effect, 3-wire
  decomposition.
- Added `OptimizeResult` to top-level public API.
- Added `atlc3 lrs` and `atlc3 sweep` CLI subcommands.

### Phase 3 — Faraday solver, full RLGC, sweeps
- Added Faraday/PEEC sparse-system solver for L and Rs
  (`atlc3.solvers.solve_lrs`).
- Added skin-depth prediction and pixel masking
  (`atlc3.solvers.skin_depth`) matching atlc2's "Restrict to skin depth".
- Added full-RLGC orchestrator (`atlc3.solvers.solve_full`) returning
  `RLGCResult` with L, C, R, G, complex Z0, εeff, vp, α, β.
- Added parameter sweep API (`atlc3.sweep`) with CLI / Python / MCP surfaces.
- Added atlc2 parity benchmark suite (`benchmarks/atlc2_parity.py`).
- MCP tools: `solve_lrs`, `solve_full`, `sweep` (long-running ones return
  `taskId`s; poll via `tasks_get`).

### Phase 2 — C/Gp bitmap solver + atlc2 file compat
- Added `Usermap` class with BMP/PNG/TIFF/JSON I/O (atlc/atlc2 compatible).
- Added per-geometry rasterizers (microstrip, stripline, CPWG, diff pairs).
- Added `MoreColors.txt` parser; JSON material packs.
- Added Laplace SOR + PyAMG multigrid solvers
  (`atlc3.solvers.laplace.solve_laplace`).
- Added charge-shift E-prediction for fast initial V-field
  (`atlc3.solvers.charge_shift`).
- Added open-boundary 8× progressive grid extension
  (`atlc3.solvers.extension`).
- Added C/Gp orchestrator with energy-integral capacitance extraction
  (`atlc3.solvers.cgp.solve_cgp`).
- Added field visualization (V/E/D/T/J + contour lines) in
  `atlc3.visualization.fields`.
- Added atlc2 `.txt` script-file interpreter
  (`atlc3.scripting.run_script_file`).
- MCP tools: `import_usermap`, `rasterize`, `solve_cgp` (async via Tasks),
  `tasks_get`, `tasks_cancel`, `run_atlc2_script`.
- MCP resources: `atlc://geometries/{id}`, `atlc://results/{id}`,
  `atlc://results/{id}/field/{V|E|D|T}`.

### Phase 1 — Closed-form analytical solvers + UX
- All 8 standard PCB geometries supported via IPC-2141A formulas
  (Hammerstad-Jensen, Wadell, Cohn, Wen).
- Differential-pair coupling correction (edge-coupled microstrip + stripline,
  broadside-coupled stripline).
- Pydantic v2 geometry models with discriminated-union JSON Schema export.
- `pint`-based unit parsing (mil, mm, in, AWG).
- atlc2's 45 standard-color material database encoded.
- CLI: `atlc3 solve / list-geometries / describe-geometry / export-schema /
  info / mcp-serve`.
- Python API: `atlc3.microstrip()`, `.stripline()`, `.cpwg()`,
  `.edge_coupled_diff()`, `.solve()`.
- MCP server: `ping`, `calculate_impedance`, `list_geometry_types`,
  `describe_geometry`, `export_geometry_schema`, plus `atlc://materials`
  resources.
- Documentation site (mkdocs-material) with quickstart, three tutorials,
  geometry reference, analytical theory.

### Phase 0 — Bootstrap
- Initial Python + Rust monorepo with maturin build, PyO3 module skeleton.
- GitHub Actions CI matrix (Linux/macOS/Windows × Python 3.11/3.12/3.13;
  ruff, black, mypy, pytest, cargo test, cargo clippy).
- cibuildwheel release pipeline → TestPyPI on tags.
- GPLv3 license, README, CONTRIBUTING, GitHub issue templates.

[Unreleased]: https://github.com/atlc3-project/atlc3/compare/v0.1.0...HEAD
