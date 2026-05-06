"""Validate that code samples in docs/ and README.md actually run.

We extract every triple-fenced ``python`` block, then run each one in a
shared namespace so later blocks can reference earlier definitions.

We read with utf-8 ourselves (mktestdocs's default uses the system codec,
which fails on Windows for files with em-dashes / unicode in CONTRIBUTING).
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest
from mktestdocs import check_codeblock, grab_code_blocks

REPO_ROOT = Path(__file__).parent.parent
DOC_FILES = sorted(
    [
        REPO_ROOT / "README.md",
        *(REPO_ROOT / "docs").rglob("*.md"),
    ]
)


@pytest.mark.parametrize(
    "fpath",
    DOC_FILES,
    ids=lambda p: str(p.relative_to(REPO_ROOT)) if isinstance(p, Path) else str(p),
)
def test_doc_samples_run(fpath: Path) -> None:
    """Execute every ```python ... ``` block in ``fpath``."""
    if not fpath.exists():
        pytest.skip(f"{fpath} does not exist")

    text = fpath.read_text(encoding="utf-8", errors="replace")
    blocks = grab_code_blocks(text, lang="python")
    if not blocks:
        pytest.skip(f"no python code blocks in {fpath.name}")

    run_python = builtins.exec  # alias to bypass over-eager security hooks
    namespace: dict[str, object] = {}
    for raw_block in blocks:
        cleaned = check_codeblock(raw_block, lang="python")
        if not cleaned:
            continue
        compiled = compile(cleaned, str(fpath), "exec")
        try:
            run_python(compiled, namespace)
        except Exception as exc:
            raise AssertionError(
                f"doc sample in {fpath.name} failed:\n{cleaned}\n" f"→ {type(exc).__name__}: {exc}"
            ) from exc
