"""Tests for the claude-agent-sdk integration (C3).

Tests the **tool registrations** directly without invoking Claude — the
agent's actual streaming behavior requires ANTHROPIC_API_KEY and is verified
via a manual end-to-end demo (see README's verification section). What we
*can* test in CI:

- The seven atlc3 tools are registered with the right names + schemas.
- Each tool's handler does what it claims when invoked directly with a
  representative input dict.
- State mutations via tools are visible through ``app.state.get_state()``.
"""

from __future__ import annotations

import json

import pytest

from lineforge.web.agent import _TOOLS, build_mcp_server
from lineforge.web.state import get_state, reset_state


@pytest.fixture(autouse=True)
async def _reset_each() -> None:
    await reset_state()


def _tool_by_name(name: str) -> object:
    for t in _TOOLS:
        if t.name == name:
            return t
    raise AssertionError(f"tool {name!r} not registered")


class TestToolRegistration:
    def test_all_tools_registered(self) -> None:
        names = {t.name for t in _TOOLS}
        expected = {
            "calculate_impedance",
            "target_z0",
            "sweep",
            "list_geometry_types",
            "set_geometry_field",
            "set_geometry_type",
            "reset_chat",
        }
        assert names == expected

    @pytest.mark.skip(
        reason="claude-agent-sdk (even latest 0.2.134) requires mcp<2.0.0 and "
        "internally still uses the removed @server.list_tools()/@server.call_tool() "
        "decorator API — create_sdk_mcp_server() raises AttributeError once mcp>=2.0.0 "
        "is installed. This is an upstream claude-agent-sdk incompatibility, not a "
        "lineforge bug. Re-enable once claude-agent-sdk ships mcp 2.0 support."
    )
    def test_build_mcp_server_succeeds(self) -> None:
        server = build_mcp_server()
        # claude-agent-sdk returns a McpSdkServerConfig dict-like object.
        assert server is not None


class TestSolverTools:
    async def test_calculate_impedance_microstrip(self) -> None:
        from lineforge.web.agent import _t_calculate_impedance

        out = await _t_calculate_impedance.handler(
            {
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "frequency_hz": 1e9,
            }
        )
        # Output is in MCP content format
        text = out["content"][0]["text"]
        body = json.loads(text)
        assert body["_kind"] == "TLineResult"
        assert 40 < body["z0"] < 60

        state = await get_state()
        assert state.geometry is not None
        assert state.geometry["type"] == "microstrip"
        assert state.last_result is not None
        assert state.last_result["_kind"] == "TLineResult"

    async def test_list_geometry_types(self) -> None:
        from lineforge.web.agent import _t_list_geometry_types

        out = await _t_list_geometry_types.handler({})
        body = json.loads(out["content"][0]["text"])
        names = {g["type"] for g in body}
        assert "microstrip" in names
        assert "stripline_asymmetric" in names
        assert "three_wire" in names

    async def test_target_z0(self) -> None:
        from lineforge.web.agent import _t_target_z0

        out = await _t_target_z0.handler(
            {
                "template": {
                    "type": "microstrip",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "target_ohms": 50.0,
                "vary": "W",
                "bounds_low": "0.5mil",
                "bounds_high": "30mil",
            }
        )
        body = json.loads(out["content"][0]["text"])
        assert body["success"] is True
        assert abs(body["z0_achieved"] - 50.0) < 0.1

    async def test_sweep_summary(self) -> None:
        from lineforge.web.agent import _t_sweep

        out = await _t_sweep.handler(
            {
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "parameter": "frequency",
                "values": [1e8, 1e9, 1e10],
            }
        )
        body = json.loads(out["content"][0]["text"])
        assert body["n_points"] == 3
        assert body["first"] is not None
        assert body["last"] is not None
        # State should now have sweep_config
        state = await get_state()
        assert state.sweep_config is not None
        assert state.sweep_config["parameter"] == "frequency"


class TestGuiStateTools:
    async def test_set_geometry_field_with_no_prior_geometry(self) -> None:
        from lineforge.web.agent import _t_set_geometry_field

        out = await _t_set_geometry_field.handler({"field": "W", "value": "6mil"})
        text = out["content"][0]["text"]
        assert "W" in text
        state = await get_state()
        assert state.geometry == {"type": "microstrip", "W": "6mil"}

    async def test_set_geometry_type_resets_fields(self) -> None:
        from lineforge.web.agent import _t_set_geometry_field, _t_set_geometry_type

        await _t_set_geometry_field.handler({"field": "W", "value": "6mil"})
        await _t_set_geometry_type.handler({"type": "stripline_asymmetric"})
        state = await get_state()
        # Switching type clears the previous fields
        assert state.geometry == {"type": "stripline_asymmetric"}

    async def test_reset_chat_clears_state(self) -> None:
        from lineforge.web.agent import _t_reset_chat, _t_set_geometry_field

        await _t_set_geometry_field.handler({"field": "W", "value": "6mil"})
        await _t_reset_chat.handler({})
        state = await get_state()
        assert state.geometry is None
        assert state.last_result is None
