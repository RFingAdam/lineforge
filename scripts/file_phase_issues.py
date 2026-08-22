"""One-time bootstrap script: file the Phase 1-4 issues from docs/plan.md.

Run with::

    python scripts/file_phase_issues.py --dry-run    # preview
    python scripts/file_phase_issues.py              # actually file

Idempotent: skips issues whose title already exists in the repo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass

REPO = "RFingAdam/atlc3"


@dataclass
class Issue:
    title: str
    milestone: int  # 2=Phase1, 3=Phase2, 4=Phase3, 5=Phase4, 6=Phase5
    label: str  # phase-1 ... phase-5
    body: str


_MILESTONE_TITLES = {
    1: "Phase 0: Bootstrap",
    2: "Phase 1: Analytical solvers + UX",
    3: "Phase 2: Bitmap C/Gp solver",
    4: "Phase 3: Faraday L/Rs solver",
    5: "Phase 4: Polish + 1.0.0 release",
    6: "Phase 5: Rust kernel acceleration",
}


def _gh_json(args: list[str]) -> object:
    out = subprocess.check_output(["gh", *args])
    return json.loads(out)


def existing_titles() -> set[str]:
    """Return all existing issue titles (open + closed) so we don't double-file."""
    items = _gh_json(
        [
            "issue",
            "list",
            "-R",
            REPO,
            "--state",
            "all",
            "--limit",
            "500",
            "--json",
            "title",
        ]
    )
    return {i["title"] for i in items}  # type: ignore[index]


def file_issue(issue: Issue, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] {issue.label} #{issue.milestone}: {issue.title}")
        return
    args = [
        "gh",
        "issue",
        "create",
        "-R",
        REPO,
        "--title",
        issue.title,
        "--body",
        issue.body,
        "--milestone",
        _MILESTONE_TITLES[issue.milestone],
        "--label",
        issue.label,
    ]
    out = subprocess.check_output(args, encoding="utf-8")
    print(f"  {out.strip()}")


# ---------------------------------------------------------------------------
# Issue catalog (excerpted from docs/plan.md AC checklists)
# ---------------------------------------------------------------------------

PHASE_1_ISSUES = [
    Issue(
        title="[1.1] Hammerstad-Jensen microstrip family",
        milestone=2,
        label="phase-1",
        body="""## Acceptance criteria

- [x] `atlc3.analytical.hammerstad.microstrip(W, T, H, er) -> TLineResult`
- [x] Embedded (coated) microstrip variant
- [x] Returns Z₀, εeff, vp, td_per_inch, conductor_loss_db_per_in
- [ ] Validated against IPC-2141A Appendix A reference table within ±0.5%
      *(currently validated at ±10% against rule-of-thumb 50Ω cases)*
- [x] Cross-checked against `skrf.media.MLine` (3 cases at ±5%)
- [x] Edge cases: W/H < 0.05 and W/H > 20 raise OutOfRangeWarning

## Status: ✅ Mostly done

Audit gap: digitize the IPC-2141A Appendix A table for ±0.5% golden tests.
""",
    ),
    Issue(
        title="[1.2] Wadell stripline (sym + asym), CPWG",
        milestone=2,
        label="phase-1",
        body="""## Acceptance criteria

- [x] `stripline_symmetric` and `stripline_asymmetric` (IPC-2141A formulas)
- [x] `cpwg` via scipy.special.ellipk (Wen 1969)
- [ ] All within ±0.5% of IPC-2141A reference values on 10+ test cases
      *(CPWG closed-form is ±15-20% accurate vs Polar SI9000: formula limitation, not a bug)*
- [x] Conductor and dielectric loss estimates included

## Status: ⚠️ Done but accuracy ceiling lower than plan target

CPWG analytical accuracy is genuinely limited. For ±0.5%, use the bitmap solver.
""",
    ),
    Issue(
        title="[1.3] Differential pairs (edge-coupled & broadside-coupled)",
        milestone=2,
        label="phase-1",
        body="""## Acceptance criteria

- [x] `edge_coupled_diff_microstrip(...) -> DiffResult`
- [x] `edge_coupled_diff_stripline`, `broadside_coupled_diff_stripline`
- [x] Zdiff = 2·Zodd, Zcommon = Zeven/2 correctness checked
- [ ] Validated against published reference values within ±1%
      *(current tolerance is ±15%: IPC-2141A coupling is empirical; for ±1% use Phase 4 direct mode solve)*

## Status: ✅ Done within IPC-2141A's accuracy limits
""",
    ),
    Issue(
        title="[1.10] Documentation site (mkdocs-material): Phase 1 content",
        milestone=2,
        label="phase-1",
        body="""## Acceptance criteria

- [x] mkdocs-material config + pages: Home, Quick Start, Tutorials, Reference, Theory
- [ ] Site builds and deploys via GitHub Pages
      *(workflow exists; never executed)*
- [ ] All code samples in tutorials tested via mktestdocs
      *(see issue [audit] mktestdocs validation)*

## Status: ⚠️ Content done; CI deploy untested
""",
    ),
]

PHASE_2_ISSUES = [
    Issue(
        title="[2.4] Usermap class: atlc/atlc2 BMP fixture coverage",
        milestone=3,
        label="phase-2",
        body="""## Acceptance criteria

- [x] `Usermap.from_bmp` reads any RGB BMP via Pillow
- [x] PNG/TIFF support
- [x] Edge replication via `replicate_edges(pad)`
- [ ] Tested with 3 atlc v1 example BMPs and 3 atlc2 example BMPs
      *(currently only synthetic test arrays: fixture work in progress)*

## Status: ⚠️ Implementation complete; external-fixture coverage missing

Closes part of AUDIT.md item #1.

## Followup

Coax + wire-pair fixtures done in tests/fixtures/geometries.py.
For full closure, also add 3 actual atlc v1 example BMPs from
http://atlc.sourceforge.net/ to tests/fixtures/usermaps/.
""",
    ),
    Issue(
        title="[2.6/2.7] Rust SOR + multigrid Laplace kernels",
        milestone=3,
        label="phase-2",
        body="""## Acceptance criteria

- [ ] `crates/atlc3_kernel/src/laplace/sor.rs` implements 5-pt FD with rayon parallelism
      *(stub only)*
- [ ] PyO3 binding `atlc3._kernel.laplace_sor(...)`
- [ ] 10× faster than NumPy on 1000×1000 microstrip
- [ ] Multigrid V-cycle ≥5× faster than SOR on 2000×2000

## Status: ❌ Not started: moved to Phase 5

The Python+NumPy+PyAMG path covers practical PCB cross-sections (a few
thousand pixels). Rust acceleration is an optimization, not a correctness gap.
""",
    ),
    Issue(
        title="[2.10] C/Gp solver: atlc v1 / atlc2 quantitative parity",
        milestone=3,
        label="phase-2",
        body="""## Acceptance criteria

- [x] `solvers.cgp.solve(usermap, options) -> CGPResult`
- [x] Energy integration C = (ε₀/V²)·∫½εE² dA (fixed in audit pass)
- [x] Reproduces analytical coax Z₀ within 10%
- [ ] Reproduces atlc v1 example C ±0.5% (no atlc v1 fixtures yet)
- [ ] Reproduces atlc2 published values ±1%

## Status: ✅ Validated against analytical references; atlc-specific parity pending

The bug found and fixed in audit pass: spurious × pixel_width² scaling
in the C-extraction made all bitmap C values 10^-10 too small.
""",
    ),
    Issue(
        title="[2.14] MCP server end-to-end Claude Desktop verification",
        milestone=3,
        label="phase-2",
        body="""## Acceptance criteria

- [x] `import_usermap`, `solve_cgp`, `tasks_get`, `tasks_cancel` tools registered
- [x] SEP-1686 Tasks pattern wired (returns taskId, status transitions)
- [ ] End-to-end: Claude Desktop loads BMP, gets impedance + V-field plot
      *(manual smoke-test only via programmatic call_tool; no live Claude Desktop test yet)*

## Status: ⚠️ Programmatic verification done; live MCP-client untested

See `docs/MCP_VERIFICATION.md` for the manual checklist.
""",
    ),
]

PHASE_3_ISSUES = [
    Issue(
        title="[3.4/3.5] Coax + round-wire DC L/R parity",
        milestone=4,
        label="phase-3",
        body="""## Acceptance criteria

- [x] DC inductance of a coax matches `(μ₀/2π)·ln(b/a)` within ±20%
      *(tightened to ±0.5% per plan needs Rust assembly + finer grid)*
- [x] Wire-pair DC L within ±25%
- [ ] Round-wire Rs at 1 GHz within ±5% of `Rs_surface = 1/(σδ·perimeter)`
- [ ] When δ ≥ 30·px, Rs accuracy ±1%

## Status: ✅ DC L validated; AC Rs validation pending

Closes part of AUDIT.md item #1.
""",
    ),
    Issue(
        title="[3.6] 3-wire decomposition (ZoR/ZoG/ZoB)",
        milestone=4,
        label="phase-3",
        body="""## Acceptance criteria

- [ ] Implement Y-decomposition per atlc2 docs §"3-wire transmission lines"
- [ ] Test against quarter-wave directional coupler reference values

## Status: ❌ Not implemented (theory page exists; code does not)
""",
    ),
    Issue(
        title="[3.7] Apply @cached to solver entry points (10× sweep speedup)",
        milestone=4,
        label="phase-3",
        body="""## Acceptance criteria

- [x] `atlc3.cache.cached` decorator exists
- [ ] Applied to `solve_cgp`, `solve_lrs`, `solve_full`
- [ ] CLI flags `--no-cache` / `--clear-cache`
- [ ] 10× sweep speedup on second run
""",
    ),
    Issue(
        title="[3.8] atlc2 parity benchmark suite",
        milestone=4,
        label="phase-3",
        body="""## Acceptance criteria

- [ ] 5 atlc2 published example cases in `benchmarks/atlc2_parity.py`
- [ ] Z₀ within 2% of atlc2's published value
- [ ] Rs within 5% of atlc2's published value
- [ ] L within 2% of atlc2's published value
- [ ] Documented in `docs/theory/atlc2_parity.md`

## Status: ⚠️ Skeleton exists; uses analytical-as-truth instead of atlc2 values

Need actual atlc2 reference outputs (run on a Windows VM, or harvest from
docs / forum posts).
""",
    ),
]

PHASE_4_ISSUES = [
    Issue(
        title="[4.1] Optimize MCP tool",
        milestone=5,
        label="phase-4",
        body="""## Acceptance criteria

- [x] CLI `atlc3 optimize ...`
- [x] Python `atlc3.optimize_for(...)`
- [ ] MCP tool: `optimize(template, target, vary, bounds) -> taskId`

## Status: ⚠️ CLI + Python done; MCP tool not registered
""",
    ),
    Issue(
        title="[4.2] Direct diff-pair odd/even mode tests",
        milestone=5,
        label="phase-4",
        body="""## Acceptance criteria

- [x] `solve_modes(usermap)` returns all 4 modes
- [x] `Zdiff_direct = 2·Zodd` (not the IPC-2141A approximation)
- [ ] Tested against published reference values within ±1%
      *(currently 0% test coverage on diff_modes.py)*
""",
    ),
    Issue(
        title="[4.5] Documentation theory pages",
        milestone=5,
        label="phase-4",
        body="""## Acceptance criteria

- [x] `docs/theory/laplace_solver.md`
- [x] `docs/theory/faraday_solver.md`
- [x] `docs/theory/skin_effect.md`
- [x] `docs/theory/three_wire.md`
- [x] All link to atlc2 ref + academic sources

## Status: ✅ Done
""",
    ),
    Issue(
        title="[4.6] PyPI 1.0.0 release",
        milestone=5,
        label="phase-4",
        body="""## Acceptance criteria

- [ ] All Phase 0–4 milestones closed
- [ ] CHANGELOG complete from 0.1.0
- [ ] Version bumped to 1.0.0
- [ ] Wheels for cp311/cp312/cp313 × 4 platforms uploaded to real PyPI
- [ ] `pip install atlc3` works on a fresh machine
- [ ] Announcement post drafted
""",
    ),
]

AUDIT_GAP_ISSUES = [
    Issue(
        title="[audit] Add mktestdocs to CI for tutorial code-sample validation",
        milestone=5,
        label="audit-gap",
        body="""From AUDIT.md item: doc samples are unverified.

## Tasks

- [ ] Add `mktestdocs` to dev dependencies
- [ ] Wire into pytest via `pytest --doctest-glob='*.md' docs/`
- [ ] Add a CI step
""",
    ),
    Issue(
        title="[audit] Document MCP-via-Claude-Desktop verification procedure",
        milestone=5,
        label="audit-gap",
        body="""From AUDIT.md item: no live MCP client test.

## Tasks

- [ ] Write `docs/MCP_VERIFICATION.md` with step-by-step Claude Desktop config
- [ ] Test microstrip query → expected Z0 ≈ 50Ω
- [ ] Test BMP upload → solve_cgp → field plot resource
- [ ] Document expected MCP request/response shapes
""",
    ),
    Issue(
        title="[audit] Build mkdocs site in CI + GitHub Pages deploy",
        milestone=2,
        label="audit-gap",
        body="""From AUDIT.md item: docs site never built.

## Tasks

- [ ] Verify `docs.yml` workflow runs `mkdocs build --strict` cleanly
- [ ] Confirm GitHub Pages deploy lands at https://rfingadam.github.io/atlc3/
""",
    ),
    Issue(
        title="[audit] Increase test coverage 58% → 90%",
        milestone=5,
        label="audit-gap",
        body="""From AUDIT.md: target was 90%, current is 58%.

## Lowest-coverage modules

- `visualization/fields.py`: 0%
- `viewer.py`: 0% (interactive: hard to test)
- `solvers/diff_modes.py`: 0%
- `solvers/extension.py`: 19%
- `mcp_server/server.py`: 29%
- `scripting/atlc2_script.py`: 46%
- `mcp_server/tasks.py`: 47%
""",
    ),
    Issue(
        title="[audit] Add CODE_OF_CONDUCT.md",
        milestone=5,
        label="polish",
        body="""From AUDIT.md item: skipped during initial commit due to a content-filter glitch. CONTRIBUTING.md currently links to the Contributor Covenant URL.

## Tasks

- [ ] Add the Contributor Covenant 2.1 text to `CODE_OF_CONDUCT.md`
- [ ] Update CONTRIBUTING.md to point at the local file
""",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Loading existing issues from", REPO)
    existing = existing_titles()
    print(f"  {len(existing)} existing issues found")

    all_issues = (
        PHASE_1_ISSUES + PHASE_2_ISSUES + PHASE_3_ISSUES + PHASE_4_ISSUES + AUDIT_GAP_ISSUES
    )

    skipped = 0
    filed = 0
    for issue in all_issues:
        if issue.title in existing:
            print(f"  [skip] already exists: {issue.title}")
            skipped += 1
            continue
        try:
            file_issue(issue, dry_run=args.dry_run)
            filed += 1
        except subprocess.CalledProcessError as exc:
            print(f"  [error] {issue.title}: {exc}")
            return 1

    print(f"\n{filed} filed, {skipped} skipped (already existed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
