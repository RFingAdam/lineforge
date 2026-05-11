# lineforge.0

Open-source, MCP-enabled, AI-friendly transmission line calculator.

lineforge.0 is the spiritual successor to David Kirkby's `atlc` and Brian
Beezley's `atlc2`. It computes the full RLGC characterization (Z₀, εeff, vp,
L, C, Rs, Gp) of any 2D transmission line cross-section — from standard PCB
geometries (microstrip, stripline, CPWG, differential pairs) to arbitrary
user-drawn bitmaps.

## What's different

- **AI-native via MCP.** First-class Model Context Protocol server lets any
  Claude/LLM agent drive the solver. Long solves use the SEP-1686 Tasks pattern.
- **Three equal surfaces.** MCP server, CLI, and Python API are all polished
  from day one.
- **Modern numerics.** Rust-accelerated SOR + multigrid Laplace solver,
  scipy.sparse + ILU-preconditioned BiCGSTAB Faraday solver. PyO3-bound inner
  loops; NumPy/SciPy for orchestration.
- **atlc2 drop-in compatible.** Existing atlc2 BMP usermaps, `MoreColors.txt`,
  and script files work unchanged. New `.lineforge.json` format is the modern
  alternative.
- **GPLv3.**

## Project status

| Phase | Goal |
|---|---|
| **0 — Bootstrap** | ✅ Repo, build system, CI, release pipeline, skeleton surfaces |
| **1 — Analytical solvers** | ✅ Hammerstad-Jensen + Wadell, all 3 surfaces |
| 2 — C and Gp solver | Bitmap kernel (Laplace FD), atlc2 compat |
| 3 — L and Rs solver | Faraday sparse solver, full RLGC, sweeps |
| 4 — Polish + 1.0.0 | Optimizer, caching, docs, PyPI release |

## Get started

- [Quick Start](quickstart.md) — first answer in three minutes
- [Python API tutorial](tutorials/python.md)
- [CLI tutorial](tutorials/cli.md)
- [MCP server tutorial](tutorials/mcp.md)
- [Geometry reference](reference/geometries.md)
- [Analytical formulas (theory)](theory/analytical.md)

## Acknowledgments

- **Dr. David Kirkby (G8WRB)** — the original `atlc`, GPL.
- **Brian Beezley (KQ6QV)** — `atlc2`, the comprehensive documented spec we
  built against.
- **scikit-rf, PyAMG, scipy.sparse** — the open-source numerical libraries
  that make this possible.
