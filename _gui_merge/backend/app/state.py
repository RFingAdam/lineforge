"""Single-user in-memory GUI state.

The GUI is intentionally local-only — one user, one session, no auth. State
lives in this module's globals; restarting the server resets it.

Both the human user (via REST + WebSocket events from the frontend) and the
chat agent (via tool calls from C3's claude-agent-sdk integration) mutate
the same state object. The frontend re-renders on every state change pushed
through ``/ws/chat`` (state-delta messages).
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GuiState(BaseModel):
    """Single source of truth for the GUI session.

    Updated by REST endpoints, by WebSocket-driven user actions, and by
    chat-agent tool calls. The state is **JSON-serializable** at all times
    so it can be broadcast verbatim over the chat WebSocket as state-delta
    messages.
    """

    model_config = ConfigDict(extra="forbid")

    geometry: dict[str, Any] | None = Field(
        None,
        description=(
            "Current geometry as a dict with a 'type' discriminator (matches "
            "atlc3.geometry.from_dict input). None = no geometry selected yet."
        ),
    )
    sweep_config: dict[str, Any] | None = Field(
        None,
        description=(
            "Sweep parameters: {parameter: 'frequency'|<field>, values: [...], "
            "solver: 'analytical'|'cgp'|'full'}. None when no sweep configured."
        ),
    )
    last_result: dict[str, Any] | None = Field(
        None,
        description="Most recent solve result (TLineResult / DiffResult / "
        "ThreeWireResult / RLGCResult — Pydantic .model_dump() output).",
    )
    last_field_plot_uri: str | None = Field(
        None,
        description="Path or data-URI of the most recent field-plot PNG.",
    )
    chat_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Append-only chat transcript: [{'role':'user'|'assistant'|"
        "'tool', 'content':...}, ...].",
    )


_state: GuiState = GuiState()
_state_lock: asyncio.Lock = asyncio.Lock()


async def get_state() -> GuiState:
    """Snapshot the current state. Cheap copy via Pydantic round-trip."""
    async with _state_lock:
        return _state.model_copy(deep=True)


async def update_state(**fields: Any) -> GuiState:
    """Atomically set the named fields and return the new snapshot."""
    global _state
    async with _state_lock:
        _state = _state.model_copy(update=fields)
        return _state.model_copy(deep=True)


async def reset_state() -> None:
    """Reset to a fresh GuiState — used by tests + the GUI's 'New design' button."""
    global _state
    async with _state_lock:
        _state = GuiState()


__all__ = ["GuiState", "get_state", "reset_state", "update_state"]
