"""Extra coverage for `web/ws_chat.py` — `_run_agent` happy path with the
agent events mocked, plus the `_handle_user_message` flow when the real
agent is enabled.

Most of the WebSocket integration is already covered by test_main.py's
TestChatWebSocket class. This file fills in the agent-mode branches (which
require ATLC3_GUI_CHAT_STUB!=1) by monkeypatching `agent.run_chat_turn` to
yield synthetic events.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lineforge.web import ws_chat
from lineforge.web.app import app
from lineforge.web.state import reset_state


@pytest.fixture(autouse=True)
async def _reset() -> None:
    await reset_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestStubMode:
    """ATLC3_GUI_CHAT_STUB=1 → echo handler; this is the default in CI."""

    def test_stub_handler_runs(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLC3_GUI_CHAT_STUB", "1")
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"role": "user", "content": "hi"}))
            reply = ws.receive_json()
        assert reply["role"] == "assistant"
        assert "(stub)" in reply["content"]


class TestAgentMode:
    """When ATLC3_GUI_CHAT_STUB!=1, `_run_agent` forwards events from
    `run_chat_turn`. We mock that function to yield synthetic events."""

    def test_agent_forwards_assistant_and_done(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLC3_GUI_CHAT_STUB", "0")

        async def _fake_run(prompt: str) -> AsyncIterator[dict[str, Any]]:
            yield {"role": "assistant", "content": "Hi there", "stream": False}
            yield {"role": "done", "stop_reason": "end_turn", "usage": None}

        # Patch at the agent module so ws_chat's import sees the fake.
        from lineforge.web import agent

        monkeypatch.setattr(agent, "run_chat_turn", _fake_run)

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"role": "user", "content": "ping"}))
            seen = []
            for _ in range(10):
                msg = ws.receive_json()
                seen.append(msg)
                if msg.get("role") == "done":
                    break
        roles = [m["role"] for m in seen]
        assert "assistant" in roles
        assert "done" in roles

    def test_agent_state_delta_broadcasts_on_tool_result(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a `tool_result` event arrives AND the state changed since the
        last snapshot, ws_chat broadcasts a `state_delta`."""
        monkeypatch.setenv("ATLC3_GUI_CHAT_STUB", "0")

        async def _fake_run(prompt: str) -> AsyncIterator[dict[str, Any]]:
            # Mutate state mid-stream so the snapshot diff triggers a delta.
            from lineforge.web.state import update_state

            await update_state(geometry={"type": "microstrip"})
            yield {"role": "tool_result", "name": "set_geometry_type", "output": "ok"}
            yield {"role": "done", "stop_reason": "end_turn", "usage": None}

        from lineforge.web import agent

        monkeypatch.setattr(agent, "run_chat_turn", _fake_run)

        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"role": "user", "content": "set up microstrip"}))
            roles = []
            for _ in range(10):
                msg = ws.receive_json()
                roles.append(msg.get("role"))
                if msg.get("role") == "done":
                    break
        # A state_delta with the new geometry should appear at least once.
        assert "state_delta" in roles


class TestIsChatDisabled:
    """`_is_chat_disabled` flips based on the env var."""

    def test_disabled_with_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLC3_GUI_CHAT_STUB", "1")
        assert ws_chat._is_chat_disabled() is True

    def test_enabled_with_env_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLC3_GUI_CHAT_STUB", "0")
        assert ws_chat._is_chat_disabled() is False

    def test_enabled_when_env_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ATLC3_GUI_CHAT_STUB", raising=False)
        assert ws_chat._is_chat_disabled() is False
