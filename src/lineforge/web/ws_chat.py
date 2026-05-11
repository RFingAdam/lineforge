"""WebSocket /ws/chat endpoint.

Wire protocol (JSON messages over WebSocket):

  Client → Server::
      {"role": "user", "content": "..."}
      {"role": "system", "type": "reset"}             # reset chat history

  Server → Client::
      {"role": "thinking", "content": "..."}
      {"role": "assistant", "content": "...", "stream": true|false}
      {"role": "tool_call", "name": "...", "input": {...}}
      {"role": "tool_result", "name": "...", "output": {...}}
      {"role": "state_delta", "patch": {...}}
      {"role": "error", "content": "..."}
      {"role": "done", "stop_reason": "...", "usage": {...}}

C3: replaces the C1 echo stub with a claude_agent_sdk-driven agent loop.
The agent has tools that mutate the shared :mod:`app.state` GuiState; after
each tool call we snapshot the state and broadcast a ``state_delta`` so the
frontend re-renders live as the agent works.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.state import get_state, reset_state, update_state

router = APIRouter()


def _is_chat_disabled() -> bool:
    """Tests / CI: set ATLC3_GUI_CHAT_STUB=1 to skip the SDK call and use the echo stub."""
    import os

    return os.environ.get("ATLC3_GUI_CHAT_STUB") == "1"


async def _run_stub(content: str, ws: WebSocket) -> str:
    """Echo handler used during tests + when ``ATLC3_GUI_CHAT_STUB=1``."""
    reply = (
        f"(stub) Got your message: {content!r}. Set ATLC3_GUI_CHAT_STUB=0 "
        "and ensure ANTHROPIC_API_KEY is set (or `claude /login` is done) "
        "to enable the real agent."
    )
    await ws.send_json({"role": "assistant", "content": reply, "stream": False})
    return reply


async def _run_agent(content: str, ws: WebSocket) -> str:
    """Run a real agent turn via claude_agent_sdk and forward events to the WS."""
    from app.agent import run_chat_turn

    last_state_snapshot = (await get_state()).model_dump()
    final_assistant_text = ""
    async for event in run_chat_turn(content):
        # Forward event verbatim
        await ws.send_json(event)
        # If the event's role indicates state may have changed, broadcast a
        # state_delta with the new snapshot.
        if event.get("role") in ("tool_result", "done"):
            snapshot = (await get_state()).model_dump()
            if snapshot != last_state_snapshot:
                await ws.send_json({"role": "state_delta", "patch": snapshot})
                last_state_snapshot = snapshot
        if event.get("role") == "assistant":
            text = event.get("content", "")
            if isinstance(text, str):
                final_assistant_text = text or final_assistant_text
    return final_assistant_text


async def _handle_user_message(content: str, ws: WebSocket) -> None:
    """Route a user message to the stub or the real agent, append to history."""
    current = await get_state()
    history = list(current.chat_history)
    history.append({"role": "user", "content": content})
    await update_state(chat_history=history)

    if _is_chat_disabled():
        reply = await _run_stub(content, ws)
    else:
        reply = await _run_agent(content, ws)

    if reply:
        # Persist the final assistant text to the GuiState's chat history.
        current = await get_state()
        history = list(current.chat_history)
        history.append({"role": "assistant", "content": reply})
        await update_state(chat_history=history)


@router.websocket("/ws/chat")
async def chat_websocket(ws: WebSocket) -> None:
    """Bidirectional chat stream."""
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError as exc:
                await ws.send_json({"role": "error", "content": f"bad JSON: {exc}"})
                continue

            role = msg.get("role")
            if role == "system" and msg.get("type") == "reset":
                await reset_state()
                await ws.send_json({"role": "state_delta", "patch": {"reset": True}})
                continue

            if role != "user":
                await ws.send_json(
                    {"role": "error", "content": f"unsupported role {role!r}"}
                )
                continue

            content = msg.get("content", "")
            await _handle_user_message(content, ws)
    except WebSocketDisconnect:
        return
