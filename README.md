# atlc3.0

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status: Pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange.svg)]()

**Open-source, MCP-enabled, AI-friendly transmission line calculator.**

atlc3.0 is the successor to David Kirkby's `atlc` (GPL, 2002) and Brian Beezley's `atlc2`
(closed-source, 2010). It computes the full RLGC characterization (Z₀, εeff, vp, L, C,
Rs, Gp) of any 2D transmission line cross-section — from standard PCB geometries
(microstrip, stripline, CPWG, differential pairs) to arbitrary user-drawn bitmaps.

What makes atlc3.0 different:

- **AI-native via MCP.** First-class [Model Context Protocol](https://modelcontextprotocol.io)
  server — any Claude / LLM agent can drive it. Long solves use the SEP-1686 Tasks pattern.
- **Three equal surfaces.** MCP server, CLI, and Python API are all polished from day one.
  Use whichever fits your workflow.
- **Modern numerics.** Rust-accelerated SOR + multigrid for the Laplace solver,
  scipy.sparse + ILU0-preconditioned BiCGSTAB for the Faraday solver. Rust kernels via
  PyO3 for inner loops; NumPy/SciPy for orchestration.
- **atlc2 drop-in compatible.** Existing atlc2 BMP usermaps, `MoreColors.txt` files, and
  script files work unchanged. New `.atlc3.json` format is the modern alternative.
- **Open source under GPLv3.**

## Status: Pre-alpha (Phase 0)

This repository is being built out in phases. Each phase is a [GitHub milestone](https://github.com/) with
explicit acceptance criteria per issue. The full plan lives in
[`docs/plan.md`](docs/plan.md).

| Phase | Status | Goal |
|---|---|---|
| 0 — Bootstrap | 🚧 in progress | Repo, build system, CI, release pipeline, skeleton surfaces |
| 1 — Analytical solvers | ⏳ pending | IPC-2141A Hammerstad-Jensen + Wadell formulas, all 3 surfaces |
| 2 — C and Gp solver | ⏳ pending | Laplace FD numerical kernel, atlc2 BMP/MoreColors/script compat |
| 3 — L and Rs solver | ⏳ pending | Faraday sparse solver, full RLGC, parameter sweeps |
| 4 — Polish + 1.0.0 | ⏳ pending | Optimizer, caching, docs, PyPI release |

## Install

> Pre-alpha — not yet on PyPI. Once Phase 0 ships:

```bash
pip install atlc3
```

For development:

```bash
git clone https://github.com/<org>/atlc3.git
cd atlc3
pip install -e ".[dev]"
```

You'll need a Rust toolchain installed for the native kernels:
<https://rustup.rs/>.

## Quick start (after Phase 1)

### Python

```python
import atlc3

result = atlc3.microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
print(f"Z0 = {result.z0:.2f} Ω, εeff = {result.eps_eff:.2f}")
```

### CLI

```bash
atlc3 solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4
```

### MCP (Claude Desktop, etc.)

Add to your MCP client config:

```json
{
  "mcpServers": {
    "atlc3": {
      "command": "atlc3",
      "args": ["mcp-serve"]
    }
  }
}
```

Then ask your assistant:

> "Calculate the impedance of a 6-mil-wide microstrip on 4-mil FR4."

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code style, and PR flow.

## Documentation

Once Phase 1 ships, full docs at <https://atlc3.readthedocs.io> (placeholder).
The plan and theory pages live in [`docs/`](docs/).

## License

[GPLv3](LICENSE). atlc3.0 references and is partially derived from David Kirkby's atlc v1
(also GPL); behavioral compatibility with atlc2 is based on its publicly documented
behavior at <http://www.hdtvprimer.com/kq6qv/atlc2.html>.

## Acknowledgments

- **Dr. David Kirkby (G8WRB)** — original `atlc`, GPL.
- **Brian Beezley (KQ6QV)** — `atlc2`, the comprehensive documented spec we built against.
- **scikit-rf, PyAMG, scipy.sparse** — the open-source numerical libraries that make this possible.
