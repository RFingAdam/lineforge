# Changelog

All notable changes to lineforge (formerly atlc3) are documented in this
file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.2.0]: 2026-05-13

### Changed

**License: GPL-3.0-or-later → AGPL-3.0-or-later.** The AGPL closes the
"wrap as a paid SaaS without contributing back" gap that GPL leaves
open (GPL's copyleft only triggers on distribution; AGPL's also triggers
on network use). The atlc / atlc2 lineage is preserved: GPL-3.0 →
AGPL-3.0 is explicitly permitted by GPL-3.0 §13. Existing GPL-3.0 forks
remain valid under their original terms; future commits and the v2.2.0
release are AGPL-3.0-or-later.

Files changed: `LICENSE` (canonical AGPLv3 text), `pyproject.toml`,
`Cargo.toml`, `src/lineforge/version.py`, README license badge.
No API changes.

### Materials database fix
- `pcb_extended.json`: corrected scalar `er`/`tan_delta` defaults for
  Isola 370HR (3.4 → 4.04, 0.005 → 0.021) and Megtron 6 R-5775
  (3.0 → 3.71, 0.001 → 0.002) to match canonical datasheet values
  at 1 GHz. The frequency-resolved `er_freq` tables were already
  correct; only the no-frequency-specified fallback was wrong.

## [2.1.0]: 2026-05-12

RF pad analytics, design-rule decision logic, and an end-to-end RF path
return-loss budget. Adds five new public APIs plus matching MCP tools.
Distilled from the L3 SIG1 stripline and 0.4 mm/0.3 mm/U.FL pad
case-study work in `examples/09_*` and `examples/10_*`.

### Added

#### RF pad capacitance analytics: `lineforge.analytical.pads`
- `pad_capacitance(W, L, h, er, method)`: finite-pad C with three
  methods: parallel-plate ("pp", lower bound), Yamashita-Atsuki square-
  pad with fringing ("ya", **default**, best for finite pads), and
  Hammerstad-Jensen wide-microstrip ("hj", upper bound).
- `pad_relief_advisor(W, L, options, band_max_ghz, rl_target_dB)`:
  ranks multiple stackup options (no relief / relieve one plane /
  relieve two planes) against an RL target at the band edge and returns
  the first option that qualifies plus full per-option comparison data.
- `PadCapResult.impedance(f)` and `.return_loss_dB(f)` for direct RL
  contribution at any frequency.
- Multi-layer dielectric input via `DielectricLayer` stacks (matches the
  existing asymmetric-stripline machinery from v1.0.0).

#### Design-rule decision logic: `lineforge.design_rules`
- `classify_pad(component_type, has_modular_grant, is_user_designed_rf,
  operating_freq_ghz)` returns one of three categories:
  - **Category 1: Follow reference design** (Wi-Fi/LTE modules with FCC
    modular grants, U.FL/SMA/MMCX connectors, RF ICs)
  - **Category 2: Optimize freely** (your own triplexers/diplexers/
    matching networks/antennas)
  - **Category 3: Standard practice** (DC, low-speed, power)
- Plus guidance text, risks-if-deviating, and references suitable for
  design review notes or agent reports.

#### Path-budget calculator: `lineforge.path_budget`
- `rf_path_budget(freq_ghz, source_pad, trace, end_pad, Z0_port)`
  combines source-pad shunt cap + trace impedance mismatch + end-pad
  shunt cap into a worst-case end-to-end RL across a frequency sweep.
- Per-frequency rows include the dominant contributor so you know which
  element to optimize first.

#### Laminate lookup: `lineforge.materials.laminates`
- `laminate_lookup(name, frequency_ghz)`: fuzzy-name match against the
  18 entries in `pcb_extended.json`. Handles aliases like "FR4 prepreg",
  "FR4 core", "RO4350B", "M6", "Megtron 6", "Isola 370HR", etc.
- `list_laminates()` returns the sorted canonical names.
- Frequency interpolation via the existing log-frequency interpolator
  when the laminate has tabulated εr/Df.

#### MCP tools (5 new)
All five new APIs are exposed as MCP tools in
`lineforge.mcp_server.server`:
- `pad_capacitance`
- `pad_relief_advisor`
- `laminate_lookup`
- `rf_path_budget`
- `classify_pad`

Total MCP tools now: 21.

#### Tests
- 51 new tests in `tests/test_analytical/test_pads.py`,
  `tests/test_laminates.py`, `tests/test_path_budget.py`,
  `tests/test_design_rules.py`.
- Total: 469 passing (up from 418 in 2.0.0).

### Changed
- Nothing breaking. All v2.0.0 APIs continue to work unchanged.

### Known issues
- Some laminate database entries (Isola 370HR, Megtron 6) have εr/Df
  values that don't match the canonical published datasheet numbers.
  Lookup tool works correctly; data correction tracked separately.

## [Unreleased: pre-2.1.0]

### Added
- **Web GUI consolidated into the main package.** The former standalone
  `atlc3-gui` sibling repo is now `lineforge.web` (importable Python
  subpackage at `src/lineforge/web/`) plus `frontend/` (Next.js dev tree)
  at the repo root. Install with `pip install 'lineforge[gui]'`; launch
  with `lineforge gui`: same chat-driven design studio, one install path.
- `[project.optional-dependencies]` group `gui`: fastapi, uvicorn[standard],
  websockets, python-dotenv, claude-agent-sdk, scikit-rf.

### Changed
- `lineforge gui` now uses the current Python interpreter (no separate
  backend venv needed) and resolves the frontend at `<repo>/frontend/`
  by default. `--gui-dir` option removed; `--frontend-dir` added for
  wheel installs that don't ship the frontend source tree.
- uvicorn import-string changed from `app.main:app` to
  `lineforge.web.app:app`. Any external scripts driving the backend
  directly need to be updated.
- Backend tests live in `tests/test_web/` and run under the unified
  `pytest` from the repo root (no separate test runner).

### Migration
- If you had the standalone `atlc3-gui` repo cloned: the standalone repo
  in your local checkout
  is preserved as the archive of granular C1–E10 commit history. Future
  development happens in this repo.

## [2.0.0]: 2026-05-11

**Project renamed: atlc3 → lineforge.** The codebase has grown past the
"successor to atlc/atlc2" framing into a programmable, agent-friendly
transmission-line platform with MCP, Touchstone export, optimizer,
multi-layer stacks, GUI, three-conductor solver, and openEMS-validated
closed-form accuracy. v2.0.0 reflects that scope.

### Breaking changes
- Python package renamed: `atlc3` → `lineforge`. Update imports:
  `from atlc3 import ...` → `from lineforge import ...`.
- CLI command renamed: `atlc3 <subcommand>` → `lineforge <subcommand>`.
- MCP server name in `claude_desktop_config.json` snippets: `atlc3` → `lineforge`.
- Rust crate renamed: `atlc3_kernel` → `lineforge_kernel`.
- Configuration file extension: `.atlc3.json` → `.lineforge.json`.
- PyPI package renamed: `pip install atlc3` → `pip install lineforge`.
  The `atlc3` package on PyPI is frozen at 1.1.0.

### Migration
For most users, three find/replaces in your project will do it:
1. `import atlc3` → `import lineforge`
2. `from atlc3` → `from lineforge`
3. `atlc3` CLI command → `lineforge`

API surface (function names, geometry models, result fields) is unchanged.

### Unchanged
- All analytical solvers (microstrip, stripline, CPWG, diff pairs, three-wire)
- All bitmap solvers (Laplace, Faraday, mode decomposition)
- atlc2 BMP / MoreColors.txt / .txt script-file drop-in compatibility
- All v1.1.0 features (multi-layer stacks, Touchstone export, optimizer,
  GUI launcher, three-conductor solver, L3 SIG1 EM validation case study)

## [1.1.0]: 2026-05-11

Three-conductor analytical solver, GUI launcher polish, and the L3 SIG1
openEMS validation case study.

### Added

#### Three-conductor lines: Y-decomposition (B1 / B2 / B3)
- `atlc3.analytical.three_wire`: closed-form Y-matrix decomposition for
  three-conductor systems (e.g. a signal trace flanked by two coplanar
  ground rails). Returns even/odd mode impedances and the full 3×3 Y
  matrix from the wire geometry. Method tag
  `analytical-three-wire-y-decomposition`.
- `atlc3.geometry.three_wire`: `WirePosition` Pydantic model and
  `ThreeConductor` geometry; supports arbitrary 2D positions per wire.
- `Laplace.solve_modes` (bitmap solver): extends 2-conductor mode
  decomposition to the 3-conductor case via Y-matrix factorisation,
  matching the analytical formula on simple geometries within ~1 %.
- Boundary-weighted floating-conductor BC (B2). When one of the wires
  is floating (Q-conserving rather than V-fixed), the Laplace solver
  now uses a boundary-weighted constraint that converges much faster
  than the previous Lagrange-multiplier approach and gives lower
  residual on coarse meshes.
- New `tests/test_analytical/test_three_wire.py` covering the
  analytical path.
- Theory doc: `docs/theory/three_wire.md`.

#### GUI ergonomics (C-final, E9)
- `atlc3 gui` CLI launcher: starts the FastAPI backend + opens the web
  UI in your default browser with one command. No more two-terminal
  startup dance.
- `atlc3 gui --reload`: runs the backend under uvicorn with auto-reload
  on source changes, for development of GUI features against a live
  atlc3 kernel. Closes #28.
- `examples/08_gui_walkthrough.md`: end-to-end walkthrough using the
  GUI for a microstrip + diff-pair + sweep workflow.

#### Case study: L3 SIG1 openEMS validation
- New `examples/09_l3_sig1_em_validation/` directory: four standalone
  openEMS scripts plus a writeup that cross-validates atlc3's Wadell
  closed-form against 3D FDTD on a real RF design point (800 MHz – 6 GHz
  triplexer common port on an 8-layer board).
- Headline results: atlc3 microstrip Z₀ matches openEMS MSLPort within
  ±1.6 % across W = 3.15 – 6.9 mil; asymmetric stripline at the design
  point matches Wadell T → 0 within −2.1 % via V/I field probes; the
  width-shift physics is reproduced within 1 Ω.

### Changed
- Nothing breaking; all 1.0.0 APIs continue to work unchanged.

## [1.0.0]: 2026-05-08

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
- `atlc3.optimize.target_z0(template, *, vary, target_ohms, ...)`.
  One-liner for "what trace width gives me 50 Ω on this stackup?"
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
- `examples/06_dielectric_stack.py`: L3 SIG1 void-L4 stackup walkthrough.
- `examples/07_touchstone_export.py`: sweep + .s2p export + skrf reload.

### Changed
- `optimize_for` 1D scalar minimization tolerance is now scaled to the
  search interval; user-visible side-effect is far tighter convergence on
  Z₀ targets (≤ 1e-9 relative error vs the previous ~1 %).
- `MaterialRecord` is forward-compatible with frequency-tabulated εr / tan_δ
  while remaining backward-compatible: existing constant-only records still
  return the same numbers from `at_frequency()` as their bulk fields.

### Phase 4: Polish + 1.0.0 prep
- Added geometry optimizer (`atlc3.optimize_for`): wrap scipy.optimize for
  finding dimensions that hit Z0 / Zdiff / εeff targets.
- Added disk-cached solves (`atlc3.cache`): repeated runs are instant.
  Disable with `ATLC3_NO_CACHE=1`.
- Theory documentation: Laplace solver, Faraday solver, skin effect, 3-wire
  decomposition.
- Added `OptimizeResult` to top-level public API.
- Added `atlc3 lrs` and `atlc3 sweep` CLI subcommands.

### Phase 3: Faraday solver, full RLGC, sweeps
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

### Phase 2: C/Gp bitmap solver + atlc2 file compat
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

### Phase 1: Closed-form analytical solvers + UX
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

### Phase 0: Bootstrap
- Initial Python + Rust monorepo with maturin build, PyO3 module skeleton.
- GitHub Actions CI matrix (Linux/macOS/Windows × Python 3.11/3.12/3.13;
  ruff, black, mypy, pytest, cargo test, cargo clippy).
- cibuildwheel release pipeline → TestPyPI on tags.
- GPLv3 license, README, CONTRIBUTING, GitHub issue templates.

[Unreleased]: https://github.com/atlc3-project/atlc3/compare/v0.1.0...HEAD
