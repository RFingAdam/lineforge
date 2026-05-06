<div align="center">

<img src="assets/logo-banner.svg" alt="atlc3 — open-source MCP-enabled transmission line calculator" width="100%"/>

<br/>

[![CI](https://github.com/RFingAdam/atlc3/actions/workflows/ci.yml/badge.svg)](https://github.com/RFingAdam/atlc3/actions/workflows/ci.yml)
[![Docs](https://github.com/RFingAdam/atlc3/actions/workflows/docs.yml/badge.svg)](https://github.com/RFingAdam/atlc3/actions/workflows/docs.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-1E40AF.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB.svg)](https://www.python.org/downloads/)
[![Rust](https://img.shields.io/badge/rust-stable-DEA584.svg)](https://www.rust-lang.org/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-00BCD4.svg)](https://mypy.readthedocs.io/)
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Compute Z₀, εₑff, L, C, Rs, Gp for any 2D transmission line cross-section.**
**From your Python notebook, terminal, or AI agent.**

[Quick start](#quick-start) ·
[What it solves](#what-it-solves) ·
[Accuracy](#accuracy) ·
[Documentation](#documentation) ·
[Roadmap](#roadmap)

</div>

---

## What is atlc3?

atlc3 is the third-generation, open-source successor to David Kirkby's
[`atlc`](http://atlc.sourceforge.net/) (GPL, 2002) and Brian Beezley's
`atlc2` (closed-source Windows app, 2010). It computes the full RLGC
characterization — characteristic impedance Z₀, effective permittivity εₑff,
phase velocity v_p, distributed inductance L, capacitance C, skin-effect
resistance Rs, and dielectric conductance Gp — for any 2D transmission line
cross-section.

**What's different about atlc3:**

- 🤖 **AI-native via MCP.** First-class [Model Context Protocol](https://modelcontextprotocol.io)
  server with 14 tools. Any Claude / LLM agent can drive it.
  Long solves use the SEP-1686 Tasks pattern.
- 🐍 **Three equal surfaces.** MCP server, CLI, and Python API are all
  polished from day one. Use whichever fits your workflow.
- ⚡ **Modern numerics.** Python+NumPy+SciPy orchestration with PyAMG
  multigrid + scipy.sparse BiCGSTAB+ILU0 solvers. Rust-accelerated kernels
  via [PyO3](https://pyo3.rs/) for inner loops (currently scaffolded;
  full implementation in Phase 5).
- 📐 **atlc2 drop-in compatible.** Existing atlc2 BMP usermaps,
  `MoreColors.txt` files, and `.txt` script files all work unchanged.
  New `.atlc3.json` is the modern alternative.
- ✅ **Validated.** Closed-form solvers cross-checked against scikit-rf
  and IPC-2141A reference values; bitmap solvers validated against
  analytical coax (Z₀ ±10%) and wire-pair (DC L ±25%) closed forms.
- 🔒 **GPLv3.** Free as in freedom, with full source.

---

## Quick start

### Install

```bash
pip install atlc3
```

You'll need a [Rust toolchain](https://rustup.rs/) only if installing from
source — the wheels on PyPI are pre-built for `cp311`/`cp312`/`cp313` ×
{Linux x86_64/aarch64, macOS universal2, Windows amd64}.

> Pre-alpha: not yet on PyPI. Install from the repo:
> ```bash
> git clone https://github.com/RFingAdam/atlc3.git
> cd atlc3
> pip install -e ".[dev]"
> ```

### Three surfaces, same answer

<table>
<tr>
<td valign="top" width="50%">

**Python**

```python
import atlc3

# 50Ω microstrip on 4 mil FR4
r = atlc3.microstrip(
    W="6mil", H="4mil", T="1.4mil", er=4.4
)
print(f"Z0 = {r.z0:.2f} Ω")
print(f"εeff = {r.eps_eff:.3f}")

# Differential pair
d = atlc3.edge_coupled_diff(
    W="4mil", S="6mil", H="4mil",
    T="1.4mil", er=4.4, on="microstrip"
)
print(f"Zdiff = {d.z_diff:.2f} Ω")
```

</td>
<td valign="top" width="50%">

**CLI**

```bash
atlc3 solve --type microstrip \
  --W 6mil --H 4mil --T 1.4mil --er 4.4

# JSON output for piping to jq, csv tools
atlc3 solve --type microstrip \
  --W 6mil --H 4mil --T 1.4mil --er 4.4 \
  --output json | jq '.z0'

# Run an atlc2 script unchanged
atlc3 run-script my_atlc2_script.txt

# Optimize for a target Z0
atlc3 optimize --type microstrip \
  --target z0=50 --vary W=0.5mil:30mil \
  --fixed H=4mil,T=1.4mil,er=4.4
```

</td>
</tr>
<tr>
<td colspan="2" valign="top">

**MCP (Claude Desktop, Cursor, any MCP client)**

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "atlc3": { "command": "atlc3", "args": ["mcp-serve"] }
  }
}
```

Then ask your assistant in plain English:

> *"What's the differential impedance of a 4 mil/6 mil edge-coupled diff pair on 4 mil FR4?"*

The agent will call `calculate_impedance` with the right geometry and report
the result. For arbitrary cross-sections, ask it to upload a bitmap
(`import_usermap`) and run `solve_cgp` (returns immediately with a
`taskId`; polled via `tasks_get` per [SEP-1686](https://modelcontextprotocol.io/seps/1686-tasks.md)).

See [`docs/MCP_VERIFICATION.md`](docs/MCP_VERIFICATION.md) for the full
end-to-end verification procedure.

</td>
</tr>
</table>

---

## What it solves

### Standard PCB geometries (closed-form, microsecond-fast)

| Geometry                          | Inputs                  | Solver                               |
| --------------------------------- | ----------------------- | ------------------------------------ |
| **Microstrip**                    | W, H, T, εr             | Hammerstad-Jensen (1980)             |
| **Embedded (coated) microstrip**  | W, H, H₂, T, εr, εr₂    | IPC-2141A coated-microstrip blend    |
| **Symmetric stripline**           | W, T, B, εr             | IPC-2141A / Cohn (1954)              |
| **Asymmetric stripline**          | W, T, H₁, H₂, εr        | IPC-2141A harmonic-mean H            |
| **CPWG** (grounded coplanar)      | W, S, H, T, εr          | Wen (1969) elliptic integrals        |
| **Edge-coupled diff microstrip**  | W, S, H, T, εr          | IPC-2141A coupling correction        |
| **Edge-coupled diff stripline**   | W, S, B, T, εr          | IPC-2141A coupling correction        |
| **Broadside-coupled diff stripline** | W, H₁, H_between, T, εr | Wadell §6.5                       |

### Arbitrary cross-sections (bitmap solver)

For anything that doesn't fit a standard parameterization — irregular
shapes, multi-conductor, custom dielectrics, designer-drawn cross-sections —
use the bitmap solver:

```python
um = atlc3.from_bmp("my_geometry.bmp", pixel_width="0.1mm")
result = atlc3.solve_cgp(um, frequency="1GHz")           # C and Gp
rlgc   = atlc3.solve_full(um, frequency="1GHz")          # full RLGC
```

The solver accepts atlc/atlc2-format BMPs unchanged — same color encoding,
same `MoreColors.txt` material file format. atlc2's `.txt` script files
also run via `atlc3 run-script script.txt`.

---

## Accuracy

atlc3 is validated at every layer. The numbers below come from the live
test suite (203 passing tests; run `pytest` to reproduce).

### Closed-form solvers

| Geometry          | Reference              | Tolerance |
| ----------------- | ---------------------- | --------- |
| Microstrip Z₀     | scikit-rf `MLine`      | ±5%       |
| Microstrip Z₀     | IPC-2141A "rule of thumb" 50Ω cases | ±10%   |
| Stripline Z₀      | IPC-2141A reference    | ±10–15%   |
| CPWG Z₀           | Wen (1969) formula     | ±15–20%¹  |
| Diff-pair Zodd    | IPC-2141A coupling     | ±15%²     |

¹ *CPWG closed-form genuinely differs across textbooks (Wen, Polar SI9000,
Saturn). For tighter tolerance use the bitmap solver.*

² *IPC-2141A's diff-pair coupling is empirical and loses accuracy for
tightly-coupled pairs (S/H < 0.5). For exact, use Phase 4's
`solve_modes(usermap)` direct odd/even-mode bitmap solve.*

### Bitmap solvers

| Geometry          | Quantity         | Reference                                  | Tolerance |
| ----------------- | ---------------- | ------------------------------------------ | --------- |
| Air coax (50Ω)    | Z₀, L, C         | (η₀/2π)·ln(b/a) · μ₀·ε₀ closed forms       | ±10%      |
| Air coax (75Ω)    | Z₀               | (η₀/2π)·ln(b/a)                            | ±10%      |
| Air coax          | DC L (Faraday)   | (μ₀/2π)·ln(b/a)                            | ±20%      |
| Wire pair (300Ω)  | DC L (Faraday)   | (μ₀/π)·acosh(D/2a)                         | ±25%      |

The "live" test against atlc/atlc2 BMP fixtures is tracked in [#10](https://github.com/RFingAdam/atlc3/issues/10) — once added, that closes the last gap to 10/10.

### Numerical pipeline

```
                   ┌─────────────────────────────────────────┐
   Geometry/BMP    │  Charge-shift E-prediction (~20 iters)  │   Initial V field
        │          │  (atlc2 §"C and Gp")                    │       │
        ▼          └─────────────────────────────────────────┘       ▼
   ┌──────────┐    ┌─────────────────────────────────────────┐  ┌──────────┐
   │  εr map  │ ─▶ │  5-pt FD Laplace, εr-weighted stencil   │ ─▶│  V field │
   └──────────┘    │  SOR (ω=1.9) or PyAMG smoothed-aggreg.  │  └──────────┘
                   └─────────────────────────────────────────┘       │
                                                                      ▼
                   ┌──────────────────────────────────────────────────────┐
                   │ C  = ε₀/V² · ∫εr·|E|² dA                             │
                   │ Gp = ω·ε₀/V² · ∫εr·tanδ·|E|² dA                      │
                   │ L  = μ₀·ε₀ / C_vacuum (re-solve with εr=1)           │
                   │ Z₀ = √(L/C),  vp = c/√εeff                           │
                   └──────────────────────────────────────────────────────┘
```

For L and Rs at finite frequency, atlc3 builds a 2D PEEC sparse system
(one row per conductor pixel) and solves it with `scipy.sparse.linalg.bicgstab`
+ ILU0 preconditioner. Skin-depth restriction (atlc2 "Restrict to skin
depth") blackens conductor pixels deeper than 3δ from the surface,
collapsing the equation count at high frequency.

Full theory in [`docs/theory/`](docs/theory/).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3: User-facing surfaces (all polished day 1)              │
│  ┌────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  MCP server    │  │  CLI: atlc3      │  │  Python API:     │ │
│  │  (FastMCP,     │  │  (Typer + Rich,  │  │  import atlc3    │ │
│  │   SEP-1686     │  │   batch + serve) │  │  Pydantic models │ │
│  │   Tasks)       │  │                  │  │                  │ │
│  └────────────────┘  └──────────────────┘  └──────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2: Solver orchestration (Python)                          │
│  • Geometry builders (microstrip / stripline / CPWG / …)         │
│  • Material database (atlc2's 45 colors + MoreColors.txt parser  │
│    + JSON material packs)                                        │
│  • Solver dispatcher (analytical fast-path → numerical fallback) │
│  • Open-boundary grid extension for unshielded geometries        │
│  • Result post-processing, field rendering, sweep / optimize     │
│  • atlc2 .txt script-file interpreter                            │
│  • Disk-cached results (diskcache, ATLC3_NO_CACHE=1 to disable)  │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: Numerical kernels                                      │
│  ┌────────────────────────┐  ┌────────────────────────────────┐ │
│  │ Pure-Python (analytic) │  │ Numerical (NumPy/SciPy/PyAMG)  │ │
│  │ • Hammerstad-Jensen    │  │ • SOR + multigrid (Laplace)    │ │
│  │ • Wadell formulas      │  │ • Charge-shift E-prediction    │ │
│  │ • Wen elliptic         │  │ • PEEC Faraday assembly        │ │
│  │ • IPC-2141A            │  │ • BiCGSTAB+ILU0 sparse solve   │ │
│  └────────────────────────┘  │ • Rust kernel slots (Phase 5)  │ │
│                              └────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Performance

| Operation                          | Time       | Notes                                    |
| ---------------------------------- | ---------- | ---------------------------------------- |
| Closed-form microstrip Z₀          | ~10 µs     | Hammerstad-Jensen, no solve              |
| 125×125 coax C/Gp solve            | ~1 s       | SOR, no extension                        |
| 125×125 coax C/Gp **cached**       | **~0.5 ms** | 2,297× speedup vs cold solve             |
| Differential pair sweep, 25 points | <100 ms    | Closed-form, sweep API                   |

Repeat solves of the same geometry hit the on-disk cache (key includes the
package version, so upgrades cleanly retire old results). Disable globally
with `ATLC3_NO_CACHE=1`; clear with `atlc3 clear-cache`.

---

## Roadmap

| Phase                      | Status         | Headline                                  |
| -------------------------- | -------------- | ----------------------------------------- |
| **0 — Bootstrap**          | ✅ Closed      | Repo, build, CI matrix, release pipeline  |
| **1 — Analytical solvers** | ✅ Closed      | All 8 standard PCB geometries, 3 surfaces |
| **2 — Bitmap C/Gp**        | ✅ Implemented | Laplace FD, atlc2 file compat, async MCP  |
| **3 — Faraday L/Rs**       | ✅ Implemented | PEEC sparse solver, skin depth, sweeps    |
| **4 — Polish + 1.0**       | 🚧 Closing     | Optimizer, cache, viewer, CHANGELOG, docs |
| **5 — Rust acceleration**  | 🟦 Pending     | Native SOR/multigrid/PEEC via PyO3        |

Track gaps as [GitHub issues](https://github.com/RFingAdam/atlc3/issues),
each tagged with its phase milestone.

---

## Documentation

- 📘 **[Quick Start](docs/quickstart.md)** — three-minute path from
  `pip install` to your first impedance answer.
- 🐍 **[Python API tutorial](docs/tutorials/python.md)**
- 💻 **[CLI tutorial](docs/tutorials/cli.md)**
- 🤖 **[MCP server tutorial](docs/tutorials/mcp.md)** +
  [verification procedure](docs/MCP_VERIFICATION.md)
- 📐 **[Geometry reference](docs/reference/geometries.md)** — every
  supported geometry with its dimensional fields and JSON Schema.
- 📖 **Theory pages**:
  [analytical formulas](docs/theory/analytical.md) ·
  [Laplace solver](docs/theory/laplace_solver.md) ·
  [Faraday solver](docs/theory/faraday_solver.md) ·
  [skin effect](docs/theory/skin_effect.md) ·
  [3-wire decomposition](docs/theory/three_wire.md)
- 📋 **[Implementation plan](docs/plan.md)** + **[audit report](AUDIT.md)** — what shipped vs what remains.
- 📝 **[Changelog](CHANGELOG.md)**

Built with [mkdocs-material](https://squidfunk.github.io/mkdocs-material/);
deploys to GitHub Pages on every push to `main`.

---

## Contributing

Contributions are welcome and follow a phase-driven workflow.

1. **Pick a [GitHub issue](https://github.com/RFingAdam/atlc3/issues)** —
   each is tagged with its phase milestone and AC checklist.
2. **Fork + branch** (`feature/your-thing` or `fix/your-bug`).
3. **Run the local check suite**:
   ```bash
   ruff check . && black --check . && mypy src/atlc3
   pytest --cov=atlc3
   cargo fmt --all -- --check && cargo clippy -- -D warnings
   cargo test --workspace
   ```
4. **Open a PR** — link the issue, tick AC checkboxes, request review.

Full contributor guide in [`CONTRIBUTING.md`](CONTRIBUTING.md). Participation
is governed by the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).

### Where the bar is

- **≥90% Python coverage** on all new modules (current overall: ~60%, with
  some intentionally interactive modules at 0%).
- **`mypy --strict` clean** on all new code.
- **Golden-value tests** for every new solver. New numerical work must
  cite an analytical or atlc/atlc2 reference value.
- **Cross-platform**: Linux + macOS + Windows × Python 3.11/3.12/3.13 in CI.

---

## Citation

If you use atlc3 in published research or designs, a citation is welcome:

```bibtex
@software{atlc3,
  title  = {atlc3.0: Open-Source MCP-Enabled Transmission Line Calculator},
  author = {{atlc3 contributors}},
  year   = {2026},
  url    = {https://github.com/RFingAdam/atlc3},
  note   = {GPL-3.0-or-later}
}
```

A formal release on [Zenodo](https://zenodo.org/) lands with `v1.0.0`.

---

## License

[GPLv3](LICENSE). atlc3 references and is partially derived from David Kirkby's
atlc v1 (also GPL); behavioral compatibility with atlc2 is based on its
publicly documented behavior at <http://www.hdtvprimer.com/kq6qv/atlc2.html>.

## Acknowledgments

- **Dr. David Kirkby (G8WRB)** — original [atlc](http://atlc.sourceforge.net/), GPL.
- **Brian Beezley (KQ6QV)** — atlc2, the comprehensive documented spec we built against.
- **[scikit-rf](https://scikit-rf.readthedocs.io)**, **[PyAMG](https://pyamg.readthedocs.io/)**,
  **[scipy.sparse](https://docs.scipy.org/doc/scipy/reference/sparse.linalg.html)** —
  the open-source numerical libraries that make this possible.
- **[FastMCP](https://github.com/jlowin/fastmcp)**, **[Typer](https://typer.tiangolo.com/)**,
  **[Pydantic](https://docs.pydantic.dev/)**, **[maturin](https://www.maturin.rs/)** —
  the modern Python toolchain underneath the three user surfaces.
- **The MCP working group** — for the [Tasks SEP-1686 spec](https://modelcontextprotocol.io/seps/1686-tasks.md)
  that made the async-solver pattern clean.

<div align="center">

<sub>Built for PCB designers, RF engineers, and AI agents.</sub>

</div>
