# lineforge — Open-Source MCP-Enabled Transmission Line Calculator

## Context

**Why this is being built.** atlc2 (kq6qv@aol.com) is a powerful but closed-source Windows-only Delphi GUI for computing the full RLGC characterization of arbitrary 2D transmission line cross-sections — the only freely available tool that predicts skin-effect Rs within ±5% for arbitrary geometries. But it is a 2010-era desktop app with no API, no automation hooks, and no path for AI agents. lineforge reimplements its two-solver architecture from physics first principles (the original `atlc` v1 GPL code is a direct reference for the Laplace kernel; atlc2's L/Rs Faraday solver is rebuilt from documented behavior), and exposes everything via a stateless MCP server, a Python API, and a CLI — all first-class from day one.

**Intended outcome:** A pip-installable Python package (with Rust-accelerated kernels) + MCP server that any Claude/LLM agent, CLI script, or Python notebook can use to characterize PCB transmission lines in seconds for standard geometries and minutes-to-hours for arbitrary cross-sections, with accuracy matching or exceeding atlc2.

## Locked-in decisions

| Decision | Choice |
|---|---|
| **License** | **GPLv3** — direct fork/reference of atlc v1 GPL kernel allowed; copyleft preserved downstream |
| **Build stack** | **Python (high-level) + Rust FFI (hot loops) from day one** — PyO3 + maturin + cibuildwheel; native speed for SOR/multigrid/Krylov inner loops, NumPy/SciPy for orchestration |
| **File formats** | **Drop-in atlc2 compat AND JSON-native format** — atlc2 BMPs + MoreColors.txt + script files work unchanged; new `.lineforge.json` is the canonical native format |
| **User surfaces** | **All polished day 1** — MCP server, CLI, Python API, all first-class. Each phase ships all three surfaces for the features in that phase |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3: User-facing surfaces (all polished day 1)              │
│  ┌────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  MCP server    │  │  CLI: lineforge      │  │  Python API:     │ │
│  │  (Python SDK,  │  │  (Click/Typer,   │  │  import lineforge    │ │
│  │   Tasks,       │  │   rich output,   │  │  (Pydantic        │ │
│  │   Resources)   │  │   batch + serve) │  │   models, typed) │ │
│  └────────────────┘  └──────────────────┘  └──────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2: Solver orchestration (Python)                          │
│  • Geometry builders (microstrip/stripline/CPWG/diff/coax/       │
│    twinlead/custom-bitmap) → Usermap                             │
│  • Material database (atlc2's 45 colors + MoreColors.txt loader  │
│    + JSON material packs)                                        │
│  • Solver dispatcher (analytical fast-path → numerical fallback) │
│  • Open-boundary 8× progressive grid extension                   │
│  • Result post-processing, field rendering, sweep/optimize       │
│  • atlc2 script-file (.txt) interpreter                          │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: Numerical kernels                                      │
│  ┌────────────────────────┐  ┌────────────────────────────────┐ │
│  │ Pure-Python (analytic) │  │ Rust kernels (PyO3-exposed)    │ │
│  │ • Hammerstad-Jensen    │  │ • SOR/Gauss-Seidel relaxation  │ │
│  │ • Wadell formulas      │  │ • Multigrid V-cycle (Laplace)  │ │
│  │ • IPC-2141A            │  │ • Sparse Faraday assembly      │ │
│  └────────────────────────┘  │ • BiCGSTAB+ILU0 (or call SciPy │ │
│                              │   for Krylov, Rust for stencil)│ │
│                              │ • Charge-shift E-prediction    │ │
│                              └────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**Stack details:**
- Python ≥3.11. Deps: `numpy`, `scipy`, `pyamg` (fallback), `pydantic`, `mcp`, `pillow`, `typer`, `rich`.
- Rust toolchain via `maturin`. Crates: `ndarray`, `rayon` (parallel inner loops), `sprs` (sparse), `pyo3`.
- CI: `cibuildwheel` matrix on Linux/macOS/Windows × Python 3.11/3.12/3.13.
- Repository: `github.com/<org>/lineforge` (single repo, monorepo of Python + Rust crate).

**MCP server design:**
- Stateless tools, each call carries the geometry blob (or a resource URI to a saved one).
- **MCP Tasks (SEP-1686)** for any solve > 2s. Tool returns `taskId`; client polls `tasks/get`.
- Resources: `atlc://geometries/{id}`, `atlc://results/{id}`, `atlc://results/{id}/field/{V|E|D|J|loss}`, `atlc://materials`, `atlc://materials/{name}`.
- Binary inputs (BMPs) as base64 strings — never host file paths.

---

## Repository layout

```
lineforge/
├── README.md
├── LICENSE                          # GPLv3
├── CONTRIBUTING.md
├── pyproject.toml                   # maturin build backend
├── Cargo.toml                       # workspace root
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                   # test matrix, lint, type-check
│   │   ├── release.yml              # cibuildwheel → PyPI
│   │   └── docs.yml                 # mkdocs deploy
│   └── ISSUE_TEMPLATE/
│       ├── phase-1-issue.md
│       ├── bug.md
│       └── feature.md
├── crates/
│   └── lineforge_kernel/                # Rust crate
│       ├── Cargo.toml
│       └── src/
│           ├── lib.rs               # PyO3 module entry
│           ├── laplace/
│           │   ├── mod.rs
│           │   ├── sor.rs           # Successive over-relaxation
│           │   └── multigrid.rs     # V-cycle multigrid
│           ├── faraday/
│           │   ├── mod.rs
│           │   ├── assemble.rs      # Sparse system construction
│           │   └── solve.rs         # BiCGSTAB + ILU0
│           ├── charge_shift.rs      # Surface-charge E-prediction
│           └── extension.rs         # 8× progressive grid extension
├── src/lineforge/
│   ├── __init__.py
│   ├── version.py
│   ├── geometry/
│   │   ├── __init__.py
│   │   ├── types.py                 # Pydantic: Microstrip, Stripline, ...
│   │   ├── builders.py              # params → Usermap rasterizer
│   │   ├── usermap.py               # Usermap class, BMP/PNG/JSON I/O
│   │   └── validation.py
│   ├── materials/
│   │   ├── __init__.py
│   │   ├── database.py              # atlc2's 45 standard colors
│   │   ├── morecolors.py            # MoreColors.txt parser
│   │   └── packs/
│   │       ├── atlc2_default.json
│   │       └── pcb_extended.json
│   ├── analytical/
│   │   ├── __init__.py
│   │   ├── hammerstad.py            # microstrip family
│   │   ├── wadell.py                # stripline, CPWG, diff
│   │   └── dispatcher.py
│   ├── solvers/
│   │   ├── __init__.py
│   │   ├── cgp.py                   # C and Gp orchestrator
│   │   ├── lrs.py                   # L and Rs orchestrator
│   │   ├── skin_depth.py            # δ prediction + masking
│   │   ├── extension.py             # Python wrapper for Rust extension
│   │   └── dispatcher.py            # analytical-vs-numerical routing
│   ├── visualization/
│   │   ├── __init__.py
│   │   └── fields.py                # V/E/D/J/loss → PNG
│   ├── results.py                   # TLineResult, RLGCResult Pydantic models
│   ├── scripting/
│   │   ├── __init__.py
│   │   └── atlc2_script.py          # atlc2 .txt script interpreter
│   ├── cli.py                       # Typer app: solve, sweep, mcp-serve, ...
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   ├── server.py                # MCP server entrypoint
│   │   ├── tools.py                 # tool implementations
│   │   ├── resources.py             # resource handlers
│   │   └── tasks.py                 # SEP-1686 Tasks lifecycle
│   └── _kernel.pyi                  # type stubs for the Rust extension
├── tests/
│   ├── conftest.py
│   ├── test_analytical/
│   ├── test_geometry/
│   ├── test_materials/
│   ├── test_solvers/
│   ├── test_cli.py
│   ├── test_mcp_server.py
│   ├── test_scripting.py
│   ├── golden/                      # IPC-2141A reference values
│   └── fixtures/
│       ├── usermaps/                # atlc v1 + atlc2 example BMPs
│       └── morecolors/
├── examples/
│   ├── 01_microstrip_python_api.py
│   ├── 02_diff_pair_cli.sh
│   ├── 03_mcp_claude_desktop.md
│   ├── 04_atlc2_bmp_import.py
│   ├── 05_parameter_sweep.py
│   └── 06_atlc2_script_compat.txt
├── docs/                            # mkdocs-material site
│   ├── index.md
│   ├── tutorials/
│   ├── reference/
│   └── theory/                      # math behind each solver
└── benchmarks/
    ├── coax_dc.py
    ├── microstrip_sweep.py
    └── atlc2_parity.py
```

---

## Phased build sequence with GitHub issues + acceptance criteria

Each phase is a **GitHub milestone**. Each issue listed becomes a GitHub issue with the acceptance criteria as a checklist in the issue body. Phases run sequentially but issues within a phase can parallelize.

---

### Phase 0 — Project bootstrap

**Milestone:** `Phase 0 — Bootstrap`  
**Goal:** Repo is alive, CI green, can pip-install an empty package, can build the Rust crate, can run an empty MCP server.

#### Issue 0.1 — Initialize repo skeleton, GPLv3 license, README
**AC:**
- [ ] GPLv3 LICENSE file present
- [ ] README has project description, status badge, install instructions placeholder
- [ ] CONTRIBUTING.md describes dev setup and PR flow
- [ ] CODE_OF_CONDUCT.md (Contributor Covenant)
- [ ] `.gitignore` covers Python, Rust, IDE files

#### Issue 0.2 — Python + Rust dual build via maturin
**AC:**
- [ ] `pyproject.toml` uses maturin as build backend
- [ ] `Cargo.toml` workspace with `crates/lineforge_kernel`
- [ ] Empty PyO3 module exports `lineforge._kernel.version()` returning a string
- [ ] `pip install -e .` works on Linux, macOS, Windows
- [ ] `python -c "from lineforge._kernel import version; print(version())"` succeeds

#### Issue 0.3 — CI matrix (lint, type-check, test, build)
**AC:**
- [ ] GitHub Actions workflow `ci.yml` runs on push and PR
- [ ] Matrix: {ubuntu-latest, macos-latest, windows-latest} × Python {3.11, 3.12, 3.13}
- [ ] Steps: ruff, black --check, mypy, pytest, cargo test, cargo clippy
- [ ] All green on initial commit

#### Issue 0.4 — Skeleton Pydantic models, empty CLI, empty MCP server
**AC:**
- [ ] `lineforge.results.TLineResult` and `lineforge.geometry.types.Microstrip` defined as Pydantic v2 models with proper field validators
- [ ] `lineforge --help` works via Typer
- [ ] `lineforge mcp-serve` starts an MCP server that exposes a single `ping` tool returning `{"status": "ok"}`
- [ ] `python -c "import lineforge; print(lineforge.__version__)"` works

#### Issue 0.5 — Release pipeline (cibuildwheel → TestPyPI on tags)
**AC:**
- [ ] `release.yml` triggered on `v*.*.*` tags
- [ ] cibuildwheel builds wheels for cp311/cp312/cp313 × {linux x86_64, linux aarch64, macos universal2, windows amd64}
- [ ] Wheels uploaded to TestPyPI
- [ ] `pip install -i https://test.pypi.org/simple/ lineforge` works on a fresh machine

---

### Phase 1 — Closed-form solvers + all three user surfaces

**Milestone:** `Phase 1 — Analytical solvers + UX`  
**Goal:** All 7 standard PCB geometries solvable via IPC-2141A, fully exposed through MCP, CLI, and Python API, all with examples and tests.

#### Issue 1.1 — Hammerstad-Jensen microstrip family
**AC:**
- [ ] `lineforge.analytical.hammerstad.microstrip(W, T, H, er) -> TLineResult` implemented
- [ ] Embedded (coated) microstrip variant included
- [ ] Returns Z₀, εeff, vp, td_per_inch, conductor_loss_db_per_in (analytical estimate)
- [ ] Validated against IPC-2141A Appendix A reference table within ±0.5%
- [ ] Cross-checked against `skrf.media.MLine` within ±1% on 10 representative cases
- [ ] Edge cases: W/H < 0.05 and W/H > 20 raise `OutOfRangeWarning`

#### Issue 1.2 — Wadell stripline (sym + asym), CPWG
**AC:**
- [ ] `lineforge.analytical.wadell.stripline_symmetric` and `..._asymmetric` implemented
- [ ] `lineforge.analytical.wadell.cpwg` implemented (uses K(k)/K(k') elliptic integrals via `scipy.special.ellipk`)
- [ ] All within ±0.5% of IPC-2141A reference values on 10+ test cases
- [ ] Conductor and dielectric loss estimates included

#### Issue 1.3 — Differential pairs (edge-coupled & broadside-coupled, microstrip & stripline)
**AC:**
- [ ] `lineforge.analytical.wadell.edge_coupled_microstrip(W, S, H, T, er)` returns `DiffResult{Z0, Zodd, Zeven, Zdiff, Zcommon, εeff_odd, εeff_even}`
- [ ] Same for `edge_coupled_stripline`, `broadside_coupled_stripline`
- [ ] `Zdiff = 2·Zodd`, `Zcommon = Zeven/2` correctness checked
- [ ] Validated against published reference values within ±1%

#### Issue 1.4 — Pydantic geometry types + JSON schema export
**AC:**
- [ ] All 7 geometry types defined as Pydantic v2 models with units (`pint` integration)
- [ ] Each type self-validates dimensional sanity (e.g. `H > 0`, `W > 0`, `er >= 1`)
- [ ] `lineforge.geometry.export_jsonschema()` returns a complete JSON Schema for the geometry union
- [ ] Round-trip: `Microstrip(...).model_dump_json()` → `Microstrip.model_validate_json(...)` lossless

#### Issue 1.5 — Analytical dispatcher
**AC:**
- [ ] `lineforge.analytical.solve(geometry: GeometryUnion) -> TLineResult` routes to the right formula based on geometry type
- [ ] Unsupported types raise `NotImplementedError` with a helpful message pointing to numerical solver (Phase 2)
- [ ] No state held; pure function

#### Issue 1.6 — CLI: `lineforge solve` for all standard geometries
**AC:**
- [ ] `lineforge solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4` prints rich-formatted results
- [ ] `lineforge solve --json geometry.json` reads geometry from a JSON file
- [ ] `lineforge solve ... --output json` writes machine-readable output
- [ ] `lineforge list-geometries` prints all supported types
- [ ] Unit suffixes (mil, mm, in, AWG) parsed via `pint` — matches atlc2's SI prefix handling
- [ ] Help text includes example invocations

#### Issue 1.7 — Python API: top-level convenience functions
**AC:**
- [ ] `lineforge.microstrip(W, H, T, er) -> TLineResult` as one-liner
- [ ] `lineforge.solve(geometry) -> TLineResult` accepts any geometry model
- [ ] All public functions have type hints and docstrings (numpy style)
- [ ] `lineforge.__all__` is curated and stable
- [ ] Documented usage in `examples/01_microstrip_python_api.py`

#### Issue 1.8 — MCP server: tools for analytical solving
**AC:**
- [ ] Tool `calculate_impedance(geometry)` accepts geometry JSON and returns `TLineResult` JSON
- [ ] Tool `list_geometry_types()` returns names + descriptions
- [ ] Tool `describe_geometry(name)` returns JSON Schema for that type
- [ ] All tools documented with descriptions, parameter schemas, and example invocations in tool metadata
- [ ] Smoke test: connect via `mcp inspector`, call each tool, verify response shape
- [ ] End-to-end test: Claude Desktop connects, asks "Z₀ for 6mil microstrip on 4mil FR4", gets ~50Ω response

#### Issue 1.9 — MCP server: Resources for material database
**AC:**
- [ ] `atlc://materials` resource returns the full atlc2 + extended material DB as JSON
- [ ] `atlc://materials/{name}` returns a single material record
- [ ] Resource list discoverable via `resources/list`

#### Issue 1.10 — Documentation site (mkdocs-material) — Phase 1 content
**AC:**
- [ ] mkdocs-material site builds and deploys via GitHub Pages
- [ ] Pages: Home, Quick Start (3 minutes to first answer), Tutorials (Python, CLI, MCP), Geometry Reference, Theory > Analytical Formulas
- [ ] All code samples in tutorials are tested via `pytest --doctest-modules` or `mktestdocs`

---

### Phase 2 — Numerical kernel: C and Gp + atlc2 file compat

**Milestone:** `Phase 2 — Bitmap solver: C and Gp`  
**Goal:** Solve arbitrary cross-sections via the Laplace FD relaxation, accept atlc2 BMPs and MoreColors.txt, expose through all three surfaces.

#### Issue 2.1 — Material database: atlc2's 45 standard colors
**AC:**
- [ ] All 45 colors from atlc2 docs encoded with exact RGB values, resistivity, εr, tanδ, μr, name
- [ ] Lookup by RGB → material works
- [ ] Reverse lookup by name → RGB works
- [ ] Tested: each documented color produces the documented material properties

#### Issue 2.2 — MoreColors.txt parser (atlc2-compatible)
**AC:**
- [ ] Parses atlc2's exact format (whitespace-delimited, `|` comments, blank lines OK)
- [ ] Tab and consecutive-blank handling matches atlc2 docs
- [ ] Loads sample MoreColors.txt from atlc2 docs without modification
- [ ] Material name preserves spaces (everything after column 8)
- [ ] Duplicates override prior definitions (last one wins, matching atlc2)
- [ ] Errors include line numbers

#### Issue 2.3 — JSON-native material packs
**AC:**
- [ ] JSON schema for material packs defined and exported
- [ ] `atlc2_default.json` and `pcb_extended.json` ship in the package
- [ ] CLI `lineforge material list / show <name> / load <pack.json>` works
- [ ] Round-trip: MoreColors.txt → JSON → MoreColors.txt produces equivalent file (semantic, not byte-exact)

#### Issue 2.4 — Usermap class: BMP/PNG/TIFF/JSON I/O
**AC:**
- [ ] `Usermap.from_bmp(path)` reads atlc2/atlc v1 BMPs unchanged
- [ ] `Usermap.from_png` and `from_tiff` work
- [ ] `Usermap.from_json` reads native format (numpy array shape + per-pixel material codes)
- [ ] `Usermap.to_bmp` writes atlc2-readable BMP
- [ ] Edge-pixel-replication semantics (atlc2: edge pixels replicated outward to 3200×3200) implemented as a method
- [ ] Tested: 3 atlc v1 example BMPs and 3 atlc2 example BMPs load with correct material assignment

#### Issue 2.5 — Geometry rasterizer (params → Usermap)
**AC:**
- [ ] `microstrip.rasterize(pixel_width)` produces a Usermap that solves to within 1% of the analytical answer (Phase 1)
- [ ] Same for stripline, CPWG, diff pairs, coax, twinlead
- [ ] `Usermap` from rasterized geometry round-trips to BMP and back losslessly

#### Issue 2.6 — Rust kernel: SOR Laplace relaxation
**AC:**
- [ ] `crates/lineforge_kernel/src/laplace/sor.rs` implements 5-pt FD Gauss-Seidel with εr-weighted stencil
- [ ] SOR ω configurable, default 1.9
- [ ] Parallel checkerboard update via `rayon`
- [ ] PyO3 binding: `lineforge._kernel.laplace_sor(grid, materials, omega, max_iter, tol) -> (V_field, n_iter, residual)`
- [ ] On a 1000×1000 microstrip, 10× faster than NumPy reference implementation
- [ ] Numerical result matches NumPy reference to 1e-9 relative

#### Issue 2.7 — Rust kernel: Multigrid V-cycle (Laplace)
**AC:**
- [ ] V-cycle multigrid implemented for the Laplace operator with εr coefficients
- [ ] On a 2000×2000 grid, ≥5× faster than SOR for the same final residual
- [ ] Falls back to PyAMG path (Python) if Rust multigrid is disabled
- [ ] Convergence verified against analytical solutions on simple geometries

#### Issue 2.8 — Rust kernel: Charge-shift E-prediction
**AC:**
- [ ] ~20-iteration boundary-charge update implemented (atlc2 docs §"C and Gp")
- [ ] Provides good initial V-field for relaxation, cutting iteration count by ≥3× on representative cases
- [ ] Toggleable via Python flag (atlc2 has "Skip E prediction" checkbox — same behavior)

#### Issue 2.9 — Open-boundary 8× progressive grid extension
**AC:**
- [ ] `extension.extend(usermap, target_size=3200)` pads usermap with 100 normal-size pixels then 8×-coarser pixels until effective area ≥3200×3200
- [ ] Result-side extraction maps coarse-grid energies back into the integrated capacitance
- [ ] On a microstrip, total C from extended grid matches infinite-half-plane analytical result within 1%

#### Issue 2.10 — C and Gp solver orchestrator
**AC:**
- [ ] `solvers.cgp.solve(usermap, options) -> CGPResult{C, Gp, V_field, vf_estimate}`
- [ ] Energy integration `C = (1/V²)·∫½εE² dA` correctly computed from V_field
- [ ] Gp from `∫ωε·tanδ·E² dA` correctly computed
- [ ] Reproduces atlc v1's published C value for at least 3 example BMPs within 0.5%
- [ ] Reproduces atlc2's published values for at least 3 example geometries within 1%

#### Issue 2.11 — Field visualization: V/E/D/loss → PNG
**AC:**
- [ ] `visualization.fields.render(field, mode)` produces PNGs matching atlc2's V/E/D/T modes visually
- [ ] Lines plot (atlc2 'L' / 'N' / 'B' keys) implemented
- [ ] Configurable colormaps; output is byte-deterministic for the same input

#### Issue 2.12 — CLI: bitmap workflow
**AC:**
- [ ] `lineforge solve --bmp usermap.bmp --pixel-width 0.1mm --method cgp` works
- [ ] `lineforge import-bmp usermap.bmp --output usermap.json` converts to native format
- [ ] `lineforge render --result result.json --field V --output v_field.png` renders fields
- [ ] All CLI commands have `--help` with examples

#### Issue 2.13 — Python API: bitmap workflow
**AC:**
- [ ] `lineforge.from_bmp("usermap.bmp", pixel_width="0.1mm").solve_cgp()` works as one-liner
- [ ] `lineforge.solve(geometry, method="cgp")` works for both rasterized and bitmap-loaded geometries
- [ ] Result objects have `.render_field("V")` returning PIL Image

#### Issue 2.14 — MCP server: async solve via Tasks (SEP-1686)
**AC:**
- [ ] Tool `import_usermap(bmp_base64, pixel_width)` returns a resource URI
- [ ] Tool `solve_cgp(geometry_or_uri, options)` returns immediately with `taskId`; emits `notifications/tasks/created`
- [ ] `tasks/get` correctly transitions `submitted → working → completed | failed`
- [ ] `tasks/result` returns the full `CGPResult` JSON
- [ ] Field plots accessible as resources `atlc://results/{id}/field/{V|E|D}`
- [ ] End-to-end: Claude Desktop loads a microstrip BMP, asks for impedance, gets a result and inline V-field image

#### Issue 2.15 — atlc2 script-file (.txt) interpreter
**AC:**
- [ ] All script commands from atlc2 docs implemented: `twinlead`, `square`, `coaxial`, `pixel`, `total`, `frequency`, `separation`, `diameter`, `insulation`, `top`, `bottom`, `side`, `skew`, `width`, `height`, `center`, `inner`, `outer`, `box`, `name`, `folder`, `open`, `solve`, `LRS`, `CGP`, `sweep`, `terminate`, `erase`, `window`, `launch`, `save`, `keyboard`, `threads`, `beep`
- [ ] Comment syntax (`|`), blank lines, whitespace handling all match atlc2
- [ ] `lineforge run-script script.txt` executes and produces equivalent outputs to atlc2
- [ ] Output files named `<name> Inductances.txt`, `<name> Capacitances.txt`, etc., match atlc2 conventions

---

### Phase 3 — Numerical kernel: L and Rs (Faraday solver)

**Milestone:** `Phase 3 — Faraday solver: L and Rs`  
**Goal:** Skin-effect resistance and inductance from sparse Faraday system, all surfaces updated with frequency-dependent RLGC.

#### Issue 3.1 — Skin-depth prediction & masking
**AC:**
- [ ] `solvers.skin_depth.compute(material, frequency) -> δ` matches `δ = sqrt(2ρ/ωμ)` exactly
- [ ] `solvers.skin_depth.mask(usermap, frequency, factor=3) -> Usermap` blackens conductor pixels >3δ from any surface
- [ ] On a 10mil thick conductor at 10 GHz, mask reduces equation count by >80%
- [ ] Toggleable via "Restrict to skin depth" flag matching atlc2

#### Issue 3.2 — Rust kernel: Sparse Faraday system assembly
**AC:**
- [ ] `crates/lineforge_kernel/src/faraday/assemble.rs` builds the N×N sparse system (one row per conductor pixel) using CSR/COO via `sprs`
- [ ] Per-conductor net-current = 0 constraint added correctly (Lagrange multiplier or row-replacement)
- [ ] Matrix exposed to Python as a `scipy.sparse.csr_matrix` (zero-copy via SciPy ↔ sprs interop or via NumPy buffers)

#### Issue 3.3 — Sparse linear solve (BiCGSTAB + ILU0)
**AC:**
- [ ] Default path uses `scipy.sparse.linalg.bicgstab` with `spilu`-derived preconditioner
- [ ] Optional Rust-native solver path for benchmarking
- [ ] Convergence tolerance configurable; default 1e-8
- [ ] On a 5000-pixel coax, solve completes in <30s on a modern laptop
- [ ] Falls back to direct solve (`scipy.sparse.linalg.spsolve`) for small (N<500) systems

#### Issue 3.4 — L extraction
**AC:**
- [ ] `solvers.lrs.extract_L(B_field, currents) = ∫½B²/μ dA / I²` correctly implemented
- [ ] DC inductance of a coax matches `L = (μ₀/2π)·ln(b/a)` within 0.5%
- [ ] Frequency-dependent L (low-frequency dispersion) reported as a function of frequency

#### Issue 3.5 — Rs extraction
**AC:**
- [ ] `solvers.lrs.extract_Rs(J_field) = ∫ρ|J|² dA / I²` correctly implemented
- [ ] Round-wire Rs at 1 GHz within 5% of `Rs_surface = 1/(σδ·perimeter)`
- [ ] When skin depth is ≥30× pixel width, Rs accuracy ±1% (matches atlc2's claim)
- [ ] When conductors are too close (per atlc2's diagram), result is flagged with a `low_confidence` warning matching atlc2's red-text behavior

#### Issue 3.6 — Full RLGC pipeline
**AC:**
- [ ] `solvers.dispatcher.solve(geometry, method="full", frequency=...) -> RLGCResult{L, C, Rs, Gp, Z0_complex, α, β, vf, ZoR, ZoG, ZoB}`
- [ ] 3-wire decomposition (ZoR, ZoG, ZoB) implemented per atlc2 docs §"3-wire transmission lines"
- [ ] Microstrip RLGC matches `skrf.media.MLine` within 2% on Z₀ and within 5% on attenuation

#### Issue 3.7 — Parameter sweeps
**AC:**
- [ ] CLI: `lineforge sweep --geometry geom.json --param frequency --values 1e6,1e7,1e8,1e9 --output sweep.csv`
- [ ] Python API: `lineforge.sweep(geometry, "frequency", values, method="full")`
- [ ] MCP tool: `sweep(geometry_or_uri, parameter, values, method) -> taskId` with task progress reporting (atlc2 logs progress to atlc2 log.txt; we expose via task notifications)
- [ ] Caches results keyed by geometry + parameter hash

#### Issue 3.8 — atlc2 parity test suite
**AC:**
- [ ] `benchmarks/atlc2_parity.py` runs 5 published atlc2 example cases
- [ ] Z₀ within 2% of atlc2's published value
- [ ] Rs within 5% of atlc2's published value
- [ ] L within 2% of atlc2's published value
- [ ] Documented in docs/theory/atlc2_parity.md

---

### Phase 4 — Advanced features, optimization, polish

**Milestone:** `Phase 4 — Advanced + Polish`  
**Goal:** Production-quality 1.0.0 release with optimization, advanced workflows, full docs.

#### Issue 4.1 — Geometry optimizer
**AC:**
- [ ] `lineforge optimize --geometry-template microstrip --target-z0 50 --er 4.4 --H 4mil --vary W` produces optimal W
- [ ] Python: `lineforge.optimize(template, target={"Z0": 50}, vary=["W"])` returns optimized geometry
- [ ] MCP tool: `optimize(template, target, vary, bounds) -> taskId`
- [ ] Uses `scipy.optimize.minimize_scalar` / `minimize` under the hood

#### Issue 4.2 — Differential pair odd/even mode direct solve
**AC:**
- [ ] `solve_differential(geometry, mode="odd"|"even"|"both")` runs the right BC configuration
- [ ] Result includes `Zdiff_direct` (not the 2·Zodd approximation) for accuracy on tightly coupled pairs
- [ ] Tested against published reference values within 1%

#### Issue 4.3 — Result caching layer
**AC:**
- [ ] All solves keyed by `(geometry_hash, options_hash, materials_hash)` cache to disk via `diskcache`
- [ ] Cache invalidation on package version bump
- [ ] CLI flag `--no-cache` and `--clear-cache`
- [ ] Cache hit reduces sweep time by 10× on the second run

#### Issue 4.4 — atlc2 GUI keyboard-command compatibility shim
**AC:**
- [ ] `lineforge view --result result.json` opens a textual viewer with atlc2's keyboard shortcuts (U/V/E/D/T/L/N/B/J/H/S/+/-/etc.)
- [ ] Field rendering matches atlc2 visual style on a sample of 3 example geometries

#### Issue 4.5 — Documentation: theory pages
**AC:**
- [ ] `docs/theory/laplace_solver.md` derives the FD stencil with εr coefficients
- [ ] `docs/theory/faraday_solver.md` derives the sparse system from Faraday's law
- [ ] `docs/theory/skin_effect.md` covers δ, the 30δ rule, and Rs accuracy bounds
- [ ] `docs/theory/three_wire.md` documents the 3-wire decomposition
- [ ] All theory pages link to atlc2's reference docs and academic sources

#### Issue 4.6 — PyPI 1.0.0 release
**AC:**
- [ ] All Phase 0–4 milestones closed
- [ ] CHANGELOG.md complete from 0.1.0 onward
- [ ] Version bumped to 1.0.0
- [ ] Wheels for cp311/cp312/cp313 × 4 platforms uploaded to real PyPI
- [ ] `pip install lineforge` works on a fresh machine
- [ ] Announcement post drafted (HN/Reddit/r/electronics/r/PrintedCircuitBoard)

---

## Verification (cross-cutting)

After each phase, all of these must pass:

1. **Unit tests** — `pytest tests/ -v --cov=lineforge` ≥ 90% coverage on Python, `cargo test` for Rust
2. **Lint/type** — `ruff check .`, `black --check .`, `mypy src/lineforge`, `cargo clippy -- -D warnings`
3. **Integration** — start MCP server, call all tools via `mcp inspector`, validate response shapes
4. **End-to-end (Phase 1+)** — Claude Desktop ↔ MCP server: ask "50Ω microstrip on 4mil FR4" → get correct W
5. **End-to-end (Phase 2+)** — Load atlc v1 example BMP → solve → C matches published value within 0.5%
6. **End-to-end (Phase 3+)** — Run `benchmarks/atlc2_parity.py` → all 5 cases within target tolerances
7. **CLI smoke** — `lineforge solve --type microstrip --W 6mil --H 4mil --er 4.4` prints results in <1s
8. **Wheel install** — Fresh VM, `pip install lineforge==<phase-version>`, run quickstart from docs

---

## Critical references (study before implementing)

- atlc v1 GPL source: <http://atlc.sourceforge.net/> — `do_fd_calculation.c`, `swap_conductor_voltages.c` are the model for the Phase 2 Laplace kernel.
- atlc2 manual: <http://www.hdtvprimer.com/kq6qv/atlc2.html> — ground-truth spec for materials, MoreColors.txt, script files, and behavioral details.
- IPC-2141A standard — Hammerstad-Jensen + Wadell formulas for Phase 1.
- B. Wadell, *Transmission Line Design Handbook*, Artech 1991 — comprehensive analytical reference.
- scikit-rf source `skrf/media/` — Python reference for closed-form media; cross-validation target.
- MCP Tasks SEP-1686: <https://modelcontextprotocol.io/seps/1686-tasks.md>
- MCP Python SDK: <https://github.com/modelcontextprotocol/python-sdk>
- PyO3 + maturin: <https://pyo3.rs/>, <https://www.maturin.rs/>
- PyAMG (multigrid fallback): <https://pyamg.readthedocs.io/>

## Reusable existing code

- **scipy.sparse.linalg** (`bicgstab`, `spilu`, `spsolve`) — Phase 3 sparse solver
- **pyamg** — Phase 2 multigrid fallback (Rust path is primary, but PyAMG is the safety net)
- **scikit-rf (BSD)** — analytical media classes for cross-validation in Phase 1 tests
- **Pillow** — BMP/PNG/TIFF I/O
- **mcp** Python SDK — server scaffolding, schema generation, Tasks support
- **pint** — unit handling (mil/mm/in/AWG suffix parsing matching atlc2)
- **Pydantic v2** — geometry/result schemas, with auto-generated JSON Schema for MCP tool definitions
- **Typer + Rich** — CLI with attractive output
- **mkdocs-material + mkdocstrings** — docs site

## Out of scope (deliberate)

- 3D full-wave EM (openEMS already does this; lineforge stays 2D cross-section)
- Ferromagnetic materials (atlc2 also doesn't handle these)
- Native GUI app (atlc2 GUI shim in Phase 4 is a CLI viewer, not a Win32 replica)
- Antenna design — explicitly out of scope, just like atlc2
