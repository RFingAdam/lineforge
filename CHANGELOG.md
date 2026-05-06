# Changelog

All notable changes to atlc3.0 are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
