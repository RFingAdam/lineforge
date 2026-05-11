"""End-to-end MCP async-tools tests using SEP-1686 Tasks pattern.

These exercise the long-running tools (`rasterize`, `solve_cgp`,
`tasks_get`) the same way Claude Desktop or `mcp inspector` would.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from lineforge.mcp_server.server import build_server


def _structured(call_result: tuple[Any, Any]) -> dict[str, Any]:
    content, structured = call_result
    if structured:
        return structured  # type: ignore[no-any-return]
    return json.loads(content[0].text)  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_rasterize_returns_uri() -> None:
    """`rasterize` should produce a usermap and return its URI."""
    server = build_server()
    result = _structured(
        await server.call_tool(
            "rasterize",
            {
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                }
            },
        )
    )
    assert "uri" in result
    assert result["uri"].startswith("atlc://geometries/")
    assert isinstance(result["shape"], list)
    assert len(result["shape"]) == 2


@pytest.mark.asyncio
async def test_solve_cgp_async_lifecycle() -> None:
    """`solve_cgp` should follow the SEP-1686 task lifecycle.

    Steps:
      1. rasterize → uri
      2. solve_cgp(uri) → taskId, status=submitted
      3. poll tasks_get until status=completed
      4. result contains a CGPResult with sane fields
    """
    server = build_server()

    # Step 1
    rasterize_out = _structured(
        await server.call_tool(
            "rasterize",
            {
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                }
            },
        )
    )
    uri = rasterize_out["uri"]

    # Step 2 — keep solve fast: skip prediction, skip the 3200x3200 padding.
    # This is the right setting for shielded geometries (or for tests).
    solve_out = _structured(
        await server.call_tool(
            "solve_cgp",
            {
                "usermap_uri": uri,
                "method": "sor",
                "use_charge_shift": False,
                "extend_grid": False,
            },
        )
    )
    assert "taskId" in solve_out
    assert solve_out["status"] in ("submitted", "working", "completed")
    task_id = solve_out["taskId"]

    # Step 3: poll
    for _ in range(60):  # up to 30 s
        await asyncio.sleep(0.5)
        status = _structured(await server.call_tool("tasks_get", {"task_id": task_id}))
        if status["status"] == "completed":
            break
        if status["status"] == "failed":
            pytest.fail(f"task failed: {status.get('error')}")
    else:
        pytest.fail(f"task did not complete; final status: {status}")

    # Step 4
    assert "result" in status
    result = status["result"]
    assert result["_kind"] == "CGPResult"
    assert result["z0"] > 0


@pytest.mark.asyncio
async def test_tasks_cancel() -> None:
    """`tasks_cancel` should mark a task as cancelled."""
    server = build_server()
    rasterize_out = _structured(
        await server.call_tool(
            "rasterize",
            {
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                }
            },
        )
    )
    submit = _structured(
        await server.call_tool(
            "solve_cgp",
            {
                "usermap_uri": rasterize_out["uri"],
                "method": "sor",
                "extend_grid": False,
            },
        )
    )
    task_id = submit["taskId"]

    cancel_out = _structured(await server.call_tool("tasks_cancel", {"task_id": task_id}))
    assert cancel_out["cancelled"] is True


@pytest.mark.asyncio
async def test_unknown_task_id_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("tasks_get", {"task_id": "not-a-real-id"}))
    assert "error" in out


@pytest.mark.asyncio
async def test_run_atlc2_script_dry_run() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "run_atlc2_script",
            {
                "script_text": "twinlead\nfrequency 1e9\nterminate\n",
                "dry_run": True,
            },
        )
    )
    assert out["ok"] is True
    assert out["geometry_kind"] == "twinlead"
