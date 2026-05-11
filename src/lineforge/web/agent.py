"""Claude Agent SDK integration — atlc3 tools + chat session driver.

Defines a set of MCP tools the agent can call to drive the GUI:

  Solver tools (read-only — exercise atlc3's library):
    - calculate_impedance(geometry, frequency?)
    - target_z0(template, target_ohms, vary?, bounds?)
    - sweep(geometry, parameter, values, solver?)
    - solve_modes(geometry)               # 3-wire Y-decomposition
    - list_geometry_types()

  GUI-state tools (write — mutate the shared GuiState so the frontend
  re-renders as the agent works):
    - set_geometry_field(field, value)
    - set_geometry_type(type)
    - reset_chat()

The session driver in :func:`run_chat_turn` opens a :class:`ClaudeSDKClient`,
sends the user prompt, and yields stream events for the WebSocket layer to
forward to the frontend.

Auth: the SDK reads ``CLAUDE_API_KEY`` from the environment, or uses the
local Claude Code CLI's stored subscription token (``setup-token`` flow)
when available. No app-level auth needed for local-only deployment.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)

from lineforge.web.state import get_state, reset_state, update_state

# --- atlc3 wrappers -----------------------------------------------------


@tool(
    "calculate_impedance",
    "Closed-form analytical Z₀ solve for any of the 9 atlc3 geometries. "
    "Input geometry must include a 'type' discriminator and the required "
    "fields for that type (e.g. microstrip needs W/H/T/er).",
    {
        "geometry": dict,
        "frequency_hz": float,
    },
)
async def _t_calculate_impedance(args: dict[str, Any]) -> dict[str, Any]:
    from lineforge.analytical import solve as analytical_solve
    from lineforge.geometry import from_dict

    geom_dict = args["geometry"]
    freq = args.get("frequency_hz")
    geom = from_dict(geom_dict)
    result = analytical_solve(geom, frequency_hz=freq)
    out = result.model_dump()
    out["_kind"] = type(result).__name__
    await update_state(geometry=geom_dict, last_result=out)
    return {"content": [{"type": "text", "text": json.dumps(out, default=str)}]}


@tool(
    "target_z0",
    "Find the dimension that lands a target characteristic impedance.",
    {
        "template": dict,
        "target_ohms": float,
        "vary": str,
        "bounds_low": str,
        "bounds_high": str,
    },
)
async def _t_target_z0(args: dict[str, Any]) -> dict[str, Any]:
    from lineforge.optimize import target_z0 as run_target

    bounds = None
    if args.get("bounds_low") and args.get("bounds_high"):
        bounds = (args["bounds_low"], args["bounds_high"])

    result = run_target(
        template=args["template"],
        vary=args.get("vary", "W"),
        target_ohms=float(args["target_ohms"]),
        bounds=bounds,
    )
    geom_dict = (
        result.geometry.model_dump()
        if hasattr(result.geometry, "model_dump")
        else dict(result.geometry)
    )
    response = {
        "geometry": geom_dict,
        "z0_achieved": result.metric.get("z0"),
        "cost": result.cost,
        "iterations": result.iterations,
        "success": result.success,
    }
    await update_state(geometry=geom_dict)
    return {"content": [{"type": "text", "text": json.dumps(response, default=str)}]}


@tool(
    "sweep",
    "Sweep one parameter (frequency, W, H, etc.) and collect results.",
    {
        "geometry": dict,
        "parameter": str,
        "values": list,
        "solver": str,
    },
)
async def _t_sweep(args: dict[str, Any]) -> dict[str, Any]:
    from lineforge.geometry import from_dict
    from lineforge.sweep import sweep as run_sweep

    geom = from_dict(args["geometry"])
    points = run_sweep(
        geom,
        parameter=args["parameter"],
        values=args["values"],
        solver=args.get("solver", "analytical"),
    )
    summary = {
        "n_points": len(points),
        "first": points[0].result.model_dump() if points else None,
        "last": points[-1].result.model_dump() if points else None,
    }
    await update_state(
        sweep_config={
            "parameter": args["parameter"],
            "values": list(args["values"]),
            "solver": args.get("solver", "analytical"),
        },
    )
    return {"content": [{"type": "text", "text": json.dumps(summary, default=str)}]}


@tool(
    "list_geometry_types",
    "List every supported atlc3 transmission-line geometry. Returns "
    "type names + class names + required fields.",
    {},
)
async def _t_list_geometry_types(args: dict[str, Any]) -> dict[str, Any]:
    from lineforge.geometry import GEOMETRY_TYPES

    out = [
        {
            "type": type_name,
            "class": cls.__name__,
            "doc": (cls.__doc__ or "").splitlines()[0].strip() if cls.__doc__ else "",
            "required_fields": [
                name
                for name, field in cls.model_fields.items()
                if field.is_required() and name != "type"
            ],
        }
        for type_name, cls in GEOMETRY_TYPES.items()
    ]
    return {"content": [{"type": "text", "text": json.dumps(out)}]}


# --- GUI-state tools ----------------------------------------------------


@tool(
    "set_geometry_field",
    "Set one field on the current GUI geometry. The frontend's geometry "
    "form re-renders automatically. Use this to populate fields one at "
    "a time so the user can watch the agent build the design live.",
    {"field": str, "value": str},
)
async def _t_set_geometry_field(args: dict[str, Any]) -> dict[str, Any]:
    state = await get_state()
    geom = dict(state.geometry) if state.geometry else {"type": "microstrip"}
    geom[args["field"]] = args["value"]
    await update_state(geometry=geom)
    return {"content": [{"type": "text", "text": f"Set {args['field']} = {args['value']!r}"}]}


@tool(
    "set_geometry_type",
    "Switch the current GUI geometry to a different type. Resets the "
    "field values; the agent should follow this with set_geometry_field "
    "calls to populate the new type's required fields.",
    {"type": str},
)
async def _t_set_geometry_type(args: dict[str, Any]) -> dict[str, Any]:
    await update_state(geometry={"type": args["type"]})
    return {"content": [{"type": "text", "text": f"Switched type to {args['type']!r}"}]}


@tool(
    "reset_chat",
    "Reset the GUI session — clear chat history, geometry, and last result.",
    {},
)
async def _t_reset_chat(args: dict[str, Any]) -> dict[str, Any]:
    await reset_state()
    return {"content": [{"type": "text", "text": "Session reset."}]}


# --- Session driver ----------------------------------------------------


_TOOLS = [
    _t_calculate_impedance,
    _t_target_z0,
    _t_sweep,
    _t_list_geometry_types,
    _t_set_geometry_field,
    _t_set_geometry_type,
    _t_reset_chat,
]


def build_mcp_server() -> Any:
    """Construct the in-process MCP server exposing all atlc3 tools."""
    return create_sdk_mcp_server(name="atlc3", version="1.0.0", tools=_TOOLS)


_SYSTEM_PROMPT = """You are an expert PCB transmission-line designer driving the
atlc3 calculator's GUI. The user describes their stackup and target Z₀ in
plain English; you call the atlc3 tools to populate the geometry form,
run the solver, and report results.

Workflow:
1. Use list_geometry_types if the user's geometry isn't obvious.
2. Use set_geometry_type to switch the GUI form to the right shape.
3. Use set_geometry_field one field at a time so the user sees the
   form populate live (W, H, T, etc.).
4. Run calculate_impedance OR target_z0 OR sweep depending on what
   the user asked for. Report the result clearly with units.

Be concise. Quote Z₀ to 3 decimals. Always show your work — when you
call a tool, the user sees the call + result in the chat.
"""


def _list_allowed_tools() -> list[str]:
    """The agent is permitted to call only the atlc3 MCP tools we registered.

    Naming convention: ``mcp__<server-name>__<tool-name>`` per the SDK.
    """
    return [f"mcp__atlc3__{t.name}" for t in _TOOLS]


async def run_chat_turn(user_prompt: str) -> AsyncIterator[dict[str, Any]]:
    """Open a one-turn chat session with the agent and yield events.

    Yields structured dicts the WebSocket handler converts to its wire
    format::

        {"role": "thinking", "content": "..."}
        {"role": "assistant", "content": "...", "stream": true|false}
        {"role": "tool_call", "name": "...", "input": {...}}
        {"role": "tool_result", "name": "...", "output": {...}}
        {"role": "done", "stop_reason": "...", "usage": {...}}
        {"role": "error", "content": "..."}

    Auth: the SDK reads CLAUDE_API_KEY from the environment, or if the
    Claude Code CLI is set up locally, uses its stored subscription token.
    Returns an error event if neither is available.
    """
    if not os.environ.get("CLAUDE_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        # Try the Claude Code CLI's stored subscription. If neither, fail
        # gracefully with a helpful message.
        try:
            import subprocess

            result = subprocess.run(
                ["claude", "--version"], capture_output=True, timeout=2, check=False
            )
            if result.returncode != 0:
                raise FileNotFoundError("claude CLI not on PATH")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            yield {
                "role": "error",
                "content": (
                    "No Claude credentials available. Set ANTHROPIC_API_KEY in the "
                    "environment, or run `claude /login` (or `claude setup-token`) to "
                    "use your subscription."
                ),
            }
            return

    server = build_mcp_server()
    options = ClaudeAgentOptions(
        mcp_servers={"atlc3": server},
        allowed_tools=_list_allowed_tools(),
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="bypassPermissions",
        max_turns=10,
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_prompt)
            async for msg in client.receive_response():
                async for event in _translate_message(msg):
                    yield event
    except Exception as exc:
        yield {"role": "error", "content": f"agent error: {exc}"}


async def _translate_message(msg: Any) -> AsyncIterator[dict[str, Any]]:
    """Map an SDK message to the WebSocket wire-format events."""
    if isinstance(msg, SystemMessage):
        return  # system init/setup, not user-visible

    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                yield {"role": "assistant", "content": block.text, "stream": False}
            elif isinstance(block, ThinkingBlock):
                yield {"role": "thinking", "content": block.thinking}
            elif isinstance(block, ToolUseBlock):
                yield {
                    "role": "tool_call",
                    "name": block.name.replace("mcp__atlc3__", ""),
                    "input": block.input,
                }
        return

    if isinstance(msg, UserMessage):
        # Tool results show up as UserMessage(content=[ToolResultBlock(...)]).
        for block in msg.content:
            if isinstance(block, ToolResultBlock):
                output: Any = block.content
                if isinstance(output, list) and output and isinstance(output[0], dict):
                    text = output[0].get("text", "")
                    try:
                        output = json.loads(text)
                    except (TypeError, json.JSONDecodeError):
                        output = text
                yield {
                    "role": "tool_result",
                    "name": "(tool)",
                    "output": output,
                }
        return

    if isinstance(msg, ResultMessage):
        yield {
            "role": "done",
            "stop_reason": getattr(msg, "stop_reason", None),
            "usage": getattr(msg, "usage", None),
        }
        return


__all__ = ["build_mcp_server", "run_chat_turn"]
