"""MCP server tests covering Phase 0 (ping) and Phase 1 (analytical tools, material resource)."""

from __future__ import annotations

import json

import pytest

from atlc3.mcp_server.server import build_server
from atlc3.version import __version__


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


@pytest.mark.asyncio
async def test_ping() -> None:
    server = build_server()
    result = await server.call_tool("ping", {})
    text = "".join(getattr(c, "text", "") for c in result if hasattr(c, "text"))
    assert "ok" in text
    assert __version__ in text


@pytest.mark.asyncio
async def test_calculate_impedance_microstrip() -> None:
    server = build_server()
    payload = {
        "geometry": {
            "type": "microstrip",
            "W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4,
        }
    }
    result = await server.call_tool("calculate_impedance", payload)
    text = "".join(getattr(c, "text", "") for c in result if hasattr(c, "text"))
    parsed = json.loads(text)
    assert "z0" in parsed
    assert 30 < parsed["z0"] < 80
    assert parsed["_kind"] == "TLineResult"


@pytest.mark.asyncio
async def test_calculate_impedance_diff_pair() -> None:
    server = build_server()
    payload = {
        "geometry": {
            "type": "edge_coupled_diff_microstrip",
            "W": "4mil", "S": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4,
        }
    }
    result = await server.call_tool("calculate_impedance", payload)
    text = "".join(getattr(c, "text", "") for c in result if hasattr(c, "text"))
    parsed = json.loads(text)
    assert "z_diff" in parsed
    assert parsed["_kind"] == "DiffResult"


@pytest.mark.asyncio
async def test_calculate_impedance_unknown_type_returns_error() -> None:
    server = build_server()
    result = await server.call_tool(
        "calculate_impedance", {"geometry": {"type": "purple-twirl"}}
    )
    text = "".join(getattr(c, "text", "") for c in result if hasattr(c, "text"))
    parsed = json.loads(text)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_list_geometry_types() -> None:
    server = build_server()
    result = await server.call_tool("list_geometry_types", {})
    text = "".join(getattr(c, "text", "") for c in result if hasattr(c, "text"))
    parsed = json.loads(text)
    types = {g["type"] for g in parsed["geometries"]}
    assert "microstrip" in types
    assert "cpwg" in types


@pytest.mark.asyncio
async def test_describe_geometry() -> None:
    server = build_server()
    result = await server.call_tool("describe_geometry", {"name": "microstrip"})
    text = "".join(getattr(c, "text", "") for c in result if hasattr(c, "text"))
    parsed = json.loads(text)
    # Should include the microstrip required fields
    required = set(parsed.get("required", []))
    assert {"W", "H", "T", "er"} <= required


@pytest.mark.asyncio
async def test_describe_unknown_geometry_returns_error() -> None:
    server = build_server()
    result = await server.call_tool("describe_geometry", {"name": "purple-twirl"})
    text = "".join(getattr(c, "text", "") for c in result if hasattr(c, "text"))
    parsed = json.loads(text)
    assert "error" in parsed
    assert "valid_types" in parsed


@pytest.mark.asyncio
async def test_materials_resource_lists_all() -> None:
    server = build_server()
    resources = await server.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "atlc://materials" in uris
