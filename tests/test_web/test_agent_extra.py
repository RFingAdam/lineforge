"""Extra coverage for `web/agent.py`: `run_chat_turn` driver and
`_translate_message` helper.

We can't actually call Claude in CI, but we can:

  - Drive `run_chat_turn` without any credentials → it yields a single
    error event and returns cleanly (no exception leak).
  - Drive `_translate_message` directly against synthetic SDK message
    objects (TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock,
    ResultMessage, SystemMessage, UserMessage) to exercise every branch
    of the message-translation logic.
"""

from __future__ import annotations

from typing import Any

import pytest

from lineforge.web import agent
from lineforge.web.state import reset_state


@pytest.fixture(autouse=True)
async def _reset() -> None:
    await reset_state()


# ---------------------------------------------------------------------------
# run_chat_turn: no credentials path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_chat_turn_without_credentials_yields_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither env var is set AND the `claude` CLI returns non-zero,
    `run_chat_turn` yields a single `{role: 'error', ...}` event and stops."""
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Patch subprocess so we don't actually run `claude --version`
    import subprocess

    def _fake_run(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("no claude")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    events = []
    async for evt in agent.run_chat_turn("hello"):
        events.append(evt)

    assert len(events) == 1
    assert events[0]["role"] == "error"
    assert "credentials" in events[0]["content"].lower()


@pytest.mark.asyncio
async def test_run_chat_turn_claude_cli_returncode_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the `claude` CLI returns a non-zero exit code, treat it the same as
    a missing CLI and yield an error event."""
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import subprocess

    class _FakeResult:
        returncode = 1

    def _fake_run(*args: Any, **kwargs: Any) -> Any:
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    # When returncode != 0, the code raises FileNotFoundError which is then
    # caught by the except (FileNotFoundError, subprocess.TimeoutExpired),
    # then yields the error event.
    events = []
    async for evt in agent.run_chat_turn("hello"):
        events.append(evt)
    assert len(events) == 1
    assert events[0]["role"] == "error"


@pytest.mark.asyncio
async def test_run_chat_turn_claude_cli_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same handling when the subprocess times out."""
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import subprocess

    def _fake_run(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=2)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    events = []
    async for evt in agent.run_chat_turn("hello"):
        events.append(evt)
    assert len(events) == 1
    assert events[0]["role"] == "error"


# ---------------------------------------------------------------------------
# _translate_message: every Claude SDK message type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_system_message_yields_nothing() -> None:
    from claude_agent_sdk import SystemMessage

    # Construct a minimal SystemMessage (subtype is permissive)
    msg = SystemMessage(subtype="setup", data={})
    events = [e async for e in agent._translate_message(msg)]
    assert events == []


@pytest.mark.asyncio
async def test_translate_assistant_text_block() -> None:
    from claude_agent_sdk import AssistantMessage, TextBlock

    msg = AssistantMessage(content=[TextBlock(text="Hello world")], model="claude-test")
    events = [e async for e in agent._translate_message(msg)]
    assert len(events) == 1
    assert events[0]["role"] == "assistant"
    assert events[0]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_translate_assistant_thinking_block() -> None:
    from claude_agent_sdk import AssistantMessage, ThinkingBlock

    msg = AssistantMessage(
        content=[ThinkingBlock(thinking="reasoning...", signature="sig")],
        model="claude-test",
    )
    events = [e async for e in agent._translate_message(msg)]
    assert len(events) == 1
    assert events[0]["role"] == "thinking"
    assert events[0]["content"] == "reasoning..."


@pytest.mark.asyncio
async def test_translate_assistant_tool_use_block() -> None:
    from claude_agent_sdk import AssistantMessage, ToolUseBlock

    msg = AssistantMessage(
        content=[ToolUseBlock(id="t1", name="mcp__atlc3__calculate_impedance", input={"x": 1})],
        model="claude-test",
    )
    events = [e async for e in agent._translate_message(msg)]
    assert len(events) == 1
    assert events[0]["role"] == "tool_call"
    # The mcp__atlc3__ prefix should be stripped
    assert events[0]["name"] == "calculate_impedance"
    assert events[0]["input"] == {"x": 1}


@pytest.mark.asyncio
async def test_translate_user_tool_result_text() -> None:
    from claude_agent_sdk import ToolResultBlock, UserMessage

    msg = UserMessage(
        content=[
            ToolResultBlock(
                tool_use_id="t1",
                content=[{"type": "text", "text": '{"z0": 50.0}'}],
                is_error=False,
            )
        ]
    )
    events = [e async for e in agent._translate_message(msg)]
    assert len(events) == 1
    assert events[0]["role"] == "tool_result"
    # JSON in the text gets parsed
    assert events[0]["output"] == {"z0": 50.0}


@pytest.mark.asyncio
async def test_translate_user_tool_result_nonjson() -> None:
    """When the tool-result text isn't valid JSON, the raw text comes through."""
    from claude_agent_sdk import ToolResultBlock, UserMessage

    msg = UserMessage(
        content=[
            ToolResultBlock(
                tool_use_id="t1",
                content=[{"type": "text", "text": "not-json"}],
                is_error=False,
            )
        ]
    )
    events = [e async for e in agent._translate_message(msg)]
    assert events[0]["output"] == "not-json"


@pytest.mark.asyncio
async def test_translate_result_message() -> None:
    from claude_agent_sdk import ResultMessage

    msg = ResultMessage(
        subtype="end_turn",
        duration_ms=1234,
        duration_api_ms=1000,
        is_error=False,
        num_turns=1,
        session_id="s1",
        total_cost_usd=0.0,
        usage={"input_tokens": 10, "output_tokens": 20},
        result="ok",
    )
    events = [e async for e in agent._translate_message(msg)]
    assert len(events) == 1
    assert events[0]["role"] == "done"
    # stop_reason / usage come from attribute access: may be None on this
    # synthetic message, but the role + key set must be present.
    assert "stop_reason" in events[0]
    assert "usage" in events[0]


# ---------------------------------------------------------------------------
# _list_allowed_tools: sanity
# ---------------------------------------------------------------------------


def test_list_allowed_tools_naming_convention() -> None:
    tools = agent._list_allowed_tools()
    # All tools are prefixed with mcp__atlc3__
    assert all(t.startswith("mcp__atlc3__") for t in tools)
    assert len(tools) == len(agent._TOOLS)
