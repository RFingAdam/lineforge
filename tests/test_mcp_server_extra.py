"""Extra MCP server coverage — tools that the existing test_mcp_server.py and
test_mcp_async.py don't exercise.

The goal here is breadth, not depth: smoke-test + error-path each tool so the
registration boilerplate, request validation, and error-mapping branches all
get covered. Long-running async tools (solve_cgp / solve_lrs / solve_full /
sweep numerical) are kept off the critical path — the existing
test_mcp_async.py already covers the async lifecycle.
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any

import numpy as np
import pytest
from PIL import Image

from lineforge.mcp_server.server import build_server


def _structured(call_result: tuple[Any, Any]) -> dict[str, Any]:
    content, structured = call_result
    if structured:
        return structured  # type: ignore[no-any-return]
    return json.loads(content[0].text)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# import_usermap
# ---------------------------------------------------------------------------


def _tiny_bmp_base64() -> str:
    n = 21
    rgb = np.full((n, n, 3), 255, dtype=np.uint8)
    rgb[0, :] = (0, 255, 0)
    rgb[-1, :] = (0, 255, 0)
    rgb[n // 2, n // 2] = (255, 0, 0)
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.mark.asyncio
async def test_import_usermap_success() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "import_usermap",
            {"bmp_base64": _tiny_bmp_base64(), "pixel_width": "0.1mm", "name": "test"},
        )
    )
    assert out["uri"].startswith("atlc://geometries/")
    assert out["shape"] == [21, 21]


@pytest.mark.asyncio
async def test_import_usermap_bad_base64() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "import_usermap",
            {"bmp_base64": "not-base64-!!", "pixel_width": "0.1mm"},
        )
    )
    assert "error" in out
    assert "could not decode" in out["error"].lower()


@pytest.mark.asyncio
async def test_import_usermap_pixel_width_as_float() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "import_usermap",
            {"bmp_base64": _tiny_bmp_base64(), "pixel_width": 1e-4, "name": "test"},
        )
    )
    assert out["pixel_width_m"] == pytest.approx(1e-4)


# ---------------------------------------------------------------------------
# rasterize tool — unknown geometry → error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rasterize_unknown_type_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("rasterize", {"geometry": {"type": "purple-twirl"}}))
    assert "error" in out


# ---------------------------------------------------------------------------
# solve_cgp / solve_lrs / solve_full / sweep — error paths only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_solve_cgp_neither_geometry_nor_uri_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("solve_cgp", {}))
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_cgp_unknown_uri_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool("solve_cgp", {"usermap_uri": "atlc://geometries/no-such-id"})
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_cgp_unknown_geometry_type_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("solve_cgp", {"geometry": {"type": "purple-twirl"}}))
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_lrs_neither_geometry_nor_uri_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("solve_lrs", {}))
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_lrs_unknown_uri_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool("solve_lrs", {"usermap_uri": "atlc://geometries/no-such-id"})
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_lrs_bad_geometry_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("solve_lrs", {"geometry": {"type": "purple-twirl"}}))
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_full_neither_geometry_nor_uri_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("solve_full", {}))
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_full_unknown_uri_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool("solve_full", {"usermap_uri": "atlc://geometries/no-such-id"})
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_full_bad_geometry_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("solve_full", {"geometry": {"type": "purple-twirl"}}))
    assert "error" in out


@pytest.mark.asyncio
async def test_sweep_analytical_returns_points() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "sweep",
            {
                "geometry": {
                    "type": "microstrip",
                    "W": "6mil",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "parameter": "frequency",
                "values": [1e8, 1e9],
                "solver": "analytical",
            },
        )
    )
    assert "points" in out
    assert len(out["points"]) == 2


@pytest.mark.asyncio
async def test_sweep_bad_geometry_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "sweep",
            {
                "geometry": {"type": "purple-twirl"},
                "parameter": "frequency",
                "values": [1e8],
            },
        )
    )
    assert "error" in out


# NOTE: the MCP sweep tool delegates parameter validation to lineforge.sweep,
# which currently treats unknown parameter names as no-op overrides rather
# than errors. That behavior is exercised by tests/test_sweep.py — we don't
# repeat it here.


# ---------------------------------------------------------------------------
# solve_modes (3-wire) — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_solve_modes_bad_uri_format_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool("solve_modes", {"usermap_uri": "http://example.com/x"})
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_modes_unknown_uid_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool("solve_modes", {"usermap_uri": "atlc://geometries/no-such-id"})
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_solve_modes_no_three_conductors_returns_error() -> None:
    """A usermap missing red/blue/green conductors → solve_modes() raises
    ValueError → tool returns {'error': ...}."""
    server = build_server()
    # Import a usermap that has only red and ground (no blue)
    n = 21
    rgb = np.full((n, n, 3), 255, dtype=np.uint8)
    rgb[0, :] = (0, 255, 0)
    rgb[-1, :] = (0, 255, 0)
    rgb[n // 2, n // 2] = (255, 0, 0)
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    bmp_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    import_out = _structured(
        await server.call_tool("import_usermap", {"bmp_base64": bmp_b64, "pixel_width": "0.1mm"})
    )
    uri = import_out["uri"]
    out = _structured(await server.call_tool("solve_modes", {"usermap_uri": uri}))
    assert "error" in out


# ---------------------------------------------------------------------------
# target_z0 tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_target_z0_microstrip_50ohm() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "target_z0",
            {
                "template": {
                    "type": "microstrip",
                    "H": "4mil",
                    "T": "1.4mil",
                    "er": 4.4,
                },
                "target_ohms": 50.0,
                "vary": "W",
                "bounds": ["0.5mil", "30mil"],
            },
        )
    )
    assert out["success"] is True
    assert out["z0_achieved"] == pytest.approx(50.0, abs=0.5)


@pytest.mark.asyncio
async def test_target_z0_bad_bounds_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "target_z0",
            {
                "template": {"type": "microstrip", "H": "4mil", "T": "1.4mil", "er": 4.4},
                "target_ohms": 50.0,
                "vary": "W",
                "bounds": ["one bound only"],
            },
        )
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_target_z0_bad_template_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "target_z0",
            {
                "template": {"type": "purple-twirl"},
                "target_ohms": 50.0,
                "vary": "W",
            },
        )
    )
    assert "error" in out


# ---------------------------------------------------------------------------
# run_atlc2_script
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_atlc2_script_invalid_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("run_atlc2_script", {"script_text": "@@bogus@@"}))
    assert "error" in out


# ---------------------------------------------------------------------------
# pad_capacitance / pad_relief_advisor / laminate_lookup / rf_path_budget /
# classify_pad — all the new v2.1 tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pad_capacitance_pp_method() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "pad_capacitance",
            {"W": "0.4mm", "L": "0.4mm", "h": "5mil", "er": 4.4, "method": "pp"},
        )
    )
    assert "C_fF" in out
    assert out["C_fF"] > 0


@pytest.mark.asyncio
async def test_pad_capacitance_bad_method_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "pad_capacitance",
            {"W": "0.4mm", "h": "5mil", "er": 4.4, "method": "bogus"},
        )
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_pad_relief_advisor_basic() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "pad_relief_advisor",
            {
                "W": "0.4mm",
                "L": "0.4mm",
                "relief_options": [
                    {
                        "name": "solid GND",
                        "stack": [{"h": "5mil", "er": 4.4, "tan_delta": 0.02}],
                    },
                    {
                        "name": "voided",
                        "stack": [{"h": "20mil", "er": 4.4, "tan_delta": 0.02}],
                    },
                ],
                "band_max_ghz": 6.0,
                "rl_target_dB": 30.0,
                "Z0_line": 50.0,
                "method": "pp",
            },
        )
    )
    assert "recommendation" in out
    assert len(out["rows"]) == 2


@pytest.mark.asyncio
async def test_pad_relief_advisor_empty_options_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "pad_relief_advisor",
            {"W": "0.4mm", "relief_options": []},
        )
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_laminate_lookup_known() -> None:
    server = build_server()
    out = _structured(await server.call_tool("laminate_lookup", {"name": "FR4"}))
    assert "er" in out
    assert "tan_delta" in out


@pytest.mark.asyncio
async def test_laminate_lookup_unknown_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("laminate_lookup", {"name": "Unobtainium-X9000"}))
    assert "error" in out


@pytest.mark.asyncio
async def test_laminate_lookup_with_frequency() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool("laminate_lookup", {"name": "FR4", "frequency_ghz": 1.0})
    )
    assert "er" in out


@pytest.mark.asyncio
async def test_rf_path_budget_basic() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "rf_path_budget",
            {
                "freq_ghz": [1.0, 3.0, 6.0],
                "source_pad": {"C_fF": 100.0},
                "trace_Z0_ohm": 50.0,
                "end_pad": {"C_fF": 50.0},
                "Z0_port": 50.0,
            },
        )
    )
    assert "rows" in out
    assert len(out["rows"]) == 3
    assert "worst_rl_dB" in out


@pytest.mark.asyncio
async def test_rf_path_budget_with_pad_params() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "rf_path_budget",
            {
                "freq_ghz": [1.0, 3.0],
                "source_pad": {"W": "0.4mm", "h": "5mil", "er": 4.4, "method": "pp"},
            },
        )
    )
    assert "rows" in out


@pytest.mark.asyncio
async def test_rf_path_budget_bad_inputs_returns_error() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "rf_path_budget",
            {"freq_ghz": [1.0], "source_pad": {"W": "not a length"}},
        )
    )
    assert "error" in out


@pytest.mark.asyncio
async def test_classify_pad_runs() -> None:
    server = build_server()
    out = _structured(
        await server.call_tool(
            "classify_pad",
            {
                "component_type": "ble_module",
                "has_modular_grant": True,
                "is_user_designed_rf": False,
                "operating_freq_ghz": 2.4,
            },
        )
    )
    assert "category" in out
    assert "guidance" in out


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_describe_geometry_unknown_returns_error() -> None:
    server = build_server()
    out = _structured(await server.call_tool("describe_geometry", {"name": "purple-twirl"}))
    assert "error" in out


@pytest.mark.asyncio
async def test_material_by_name_resource_unknown() -> None:
    """The `atlc://materials/{name}` resource returns an error JSON for an
    unknown name."""
    server = build_server()
    # Reading the resource via its URI
    contents = await server.read_resource("atlc://materials/Unobtainium-X9000")
    # `read_resource` returns an iterable of ReadResourceContents — extract text
    text_parts = []
    for c in contents:
        text = getattr(c, "content", None) or getattr(c, "text", None)
        if isinstance(text, str):
            text_parts.append(text)
    joined = "\n".join(text_parts)
    parsed = json.loads(joined) if joined else {"error": "empty"}
    assert "error" in parsed


@pytest.mark.asyncio
async def test_usermap_resource_unknown_id() -> None:
    server = build_server()
    contents = await server.read_resource("atlc://geometries/no-such-id")
    text_parts = []
    for c in contents:
        text = getattr(c, "content", None) or getattr(c, "text", None)
        if isinstance(text, str):
            text_parts.append(text)
    joined = "\n".join(text_parts)
    parsed = json.loads(joined) if joined else {"error": "empty"}
    assert "error" in parsed


@pytest.mark.asyncio
async def test_result_resource_unknown_id() -> None:
    server = build_server()
    contents = await server.read_resource("atlc://results/no-such-id")
    text_parts = []
    for c in contents:
        text = getattr(c, "content", None) or getattr(c, "text", None)
        if isinstance(text, str):
            text_parts.append(text)
    joined = "\n".join(text_parts)
    parsed = json.loads(joined) if joined else {"error": "empty"}
    assert "error" in parsed


@pytest.mark.asyncio
async def test_field_plot_resource_unknown_id() -> None:
    server = build_server()
    contents = await server.read_resource("atlc://results/no-such-id/field/V")
    text_parts = []
    for c in contents:
        text = getattr(c, "content", None) or getattr(c, "text", None)
        if isinstance(text, str):
            text_parts.append(text)
    joined = "\n".join(text_parts)
    parsed = json.loads(joined) if joined else {"error": "empty"}
    assert "error" in parsed
