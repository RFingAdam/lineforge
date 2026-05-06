# Contributing to atlc3.0

Thanks for your interest in atlc3.0. This guide covers how to get a development
environment running, the code-style + testing expectations, and the PR flow.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). In short: be kind.

## Project layout

```
atlc3/
├── crates/atlc3_kernel/   # Rust crate (PyO3-exposed numerical kernels)
├── src/atlc3/             # Python package (orchestration, surfaces)
├── tests/                 # pytest suite
├── examples/              # runnable examples for users
├── benchmarks/            # performance + parity benchmarks
└── docs/                  # mkdocs-material site
```

## Dev environment

You need:

- **Python 3.11+** (3.13 recommended).
- **Rust toolchain** via <https://rustup.rs/> (stable channel).
- **maturin** for building the mixed Python/Rust package.

```bash
git clone https://github.com/<org>/atlc3.git
cd atlc3

python -m venv .venv
source .venv/bin/activate     # macOS/Linux
# OR: .venv\Scripts\activate  # Windows PowerShell

pip install --upgrade pip maturin
pip install -e ".[dev]"       # editable install with dev deps
```

This builds the Rust kernel (`atlc3._kernel`) in debug mode and links it into your
editable Python install. To rebuild after Rust changes:

```bash
maturin develop                # debug
maturin develop --release      # optimized
```

## Code style

Python:

- **Formatter:** `black`
- **Linter:** `ruff` (config in `pyproject.toml`)
- **Type-checker:** `mypy --strict` for `src/atlc3/`
- **Docstrings:** NumPy style, public APIs only

Rust:

- **Formatter:** `cargo fmt`
- **Linter:** `cargo clippy -- -D warnings`
- **Style:** standard Rust, prefer iterator chains, `rayon` for parallelism

Run all checks before opening a PR:

```bash
ruff check . && black --check . && mypy src/atlc3
cargo fmt -- --check && cargo clippy -- -D warnings
```

## Testing

```bash
pytest                           # full suite
pytest tests/test_analytical/    # one module
pytest -k microstrip             # filter by name
pytest --cov=atlc3 --cov-report=term-missing
cargo test                       # Rust unit tests
```

We require **≥ 90% Python coverage** and clean clippy on all PRs.

For numerical work, every solver has **golden-value tests** — IPC-2141A reference
tables, scikit-rf cross-checks, or atlc/atlc2 published example values. New solvers
must come with golden tests.

## Phased roadmap

The repo follows a phased plan documented in [`docs/plan.md`](docs/plan.md). Each
phase is a GitHub milestone; each issue has explicit acceptance-criteria checklists.
Please target your PRs at open issues so the AC list can be ticked off.

### Picking an issue

- **Good first issues** are labeled `good first issue`.
- **Phase 0/1 work** is the easiest entry point — analytical formulas, Pydantic
  models, CLI wiring.
- **Numerical kernel work** (Phase 2/3) requires familiarity with sparse linear
  algebra and FD methods.
- **MCP server work** is welcome at any phase.

## PR flow

1. Open an issue (or comment on an existing one) before starting non-trivial work.
2. Fork + branch (`feature/your-thing` or `fix/your-bug`).
3. Make your changes with tests.
4. Run the full check suite locally.
5. Open the PR, link the issue with `Closes #N`, and tick AC checkboxes.
6. CI must be green; one maintainer review minimum.

## Licensing

By contributing, you agree your contributions are licensed under [GPLv3](LICENSE).
atlc3.0 references and is partially derived from David Kirkby's GPL atlc v1; we
preserve copyleft on all derivatives.

## Reporting bugs

Open an issue with:

- A minimal reproduction (geometry params or a small BMP).
- Expected vs actual results.
- atlc3 version, Python version, OS.

For numerical accuracy bugs, please include the analytical or atlc/atlc2 reference
value you're comparing against.
