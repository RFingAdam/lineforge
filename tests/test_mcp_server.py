"""MCP server tests covering Phase 0 (ping) and Phase 1 (analytical tools, material resource).

FastMCP 1.27's ``call_tool`` returns a 2-tuple of (content_list,
structured_content). Tests below use the structured-content path which is
already a parsed dict. No JSON re-parsing needed.
"""

from __future__ import annotations

from typing import Any

import pytest

from lineforge.mcp_server.server import build_server
from lineforge.version import __version__


def test_server_builds() -> None:
    assert build_server() is not None


@pytest.mark.asyncio
async def test_phase1_tools_registered() -> None:
    server = build_server()
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert {
        "ping",
        "calculate_impedance",
        "list_geometry_types",
        "describe_geometry",
        "export_geometry_schema",
    } <= names


def _structured(call_result: tuple[Any, Any]) -> dict[str, Any]:
    """Extract the structured-content dict from FastMCP's call_tool result."""
    content, structured = call_result
    if structured:
        return structured  # type: ignore[no-any-return]
    # Fallback: parse the JSON text from the first content block
    import json

    return json.loads(content[0].text)  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_ping() -> None:
    server = build_server()
    parsed = _structured(await server.call_tool("ping", {}))
    assert parsed["status"] == "ok"
    assert parsed["version"] == __version__


@pytest.mark.asyncio
async def test_calculate_impedance_microstrip() -> None:
    server = build_server()
    payload = {
        "geometry": {
            "type": "microstrip",
            "W": "6mil",
            "H": "4mil",
            "T": "1.4mil",
            "er": 4.4,
        }
    }
    parsed = _structured(await server.call_tool("calculate_impedance", payload))
    assert "z0" in parsed
    assert 30 < parsed["z0"] < 80
    assert parsed["_kind"] == "TLineResult"


@pytest.mark.asyncio
async def test_calculate_impedance_diff_pair() -> None:
    server = build_server()
    payload = {
        "geometry": {
            "type": "edge_coupled_diff_microstrip",
            "W": "4mil",
            "S": "6mil",
            "H": "4mil",
            "T": "1.4mil",
            "er": 4.4,
        }
    }
    parsed = _structured(await server.call_tool("calculate_impedance", payload))
    assert "z_diff" in parsed
    assert parsed["_kind"] == "DiffResult"


@pytest.mark.asyncio
async def test_calculate_impedance_unknown_type_returns_error() -> None:
    server = build_server()
    parsed = _structured(
        await server.call_tool("calculate_impedance", {"geometry": {"type": "purple-twirl"}})
    )
    assert "error" in parsed


@pytest.mark.asyncio
async def test_list_geometry_types() -> None:
    server = build_server()
    parsed = _structured(await server.call_tool("list_geometry_types", {}))
    types = {g["type"] for g in parsed["geometries"]}
    assert "microstrip" in types
    assert "cpwg" in types


@pytest.mark.asyncio
async def test_describe_geometry() -> None:
    server = build_server()
    parsed = _structured(await server.call_tool("describe_geometry", {"name": "microstrip"}))
    required = set(parsed.get("required", []))
    assert {"W", "H", "T", "er"} <= required


@pytest.mark.asyncio
async def test_describe_unknown_geometry_returns_error() -> None:
    server = build_server()
    parsed = _structured(await server.call_tool("describe_geometry", {"name": "purple-twirl"}))
    assert "error" in parsed
    assert "valid_types" in parsed


@pytest.mark.asyncio
async def test_materials_resource_lists_all() -> None:
    server = build_server()
    resources = await server.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "atlc://materials" in uris
