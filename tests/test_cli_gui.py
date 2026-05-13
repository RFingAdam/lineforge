"""Smoke tests for the `lineforge gui` CLI helpers.

These tests exercise the small, unit-testable building blocks added to
``lineforge.cli`` (port selection, Node toolchain detection, backend health
polling). They intentionally do **not** spawn uvicorn or Next.js — those are
integration concerns. Subprocess and network calls are mocked.
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest
import typer

from lineforge.cli import (
    _check_node_toolchain,
    _pick_port,
    _wait_for_backend,
)

# ---------------------------------------------------------------------------
# _pick_port
# ---------------------------------------------------------------------------


def _bind_and_hold(port: int) -> socket.socket:
    """Bind a socket to 127.0.0.1:port and return it so the caller can close."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


def _find_free_port() -> int:
    """Ask the OS for a random free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_pick_port_returns_preferred_when_free() -> None:
    port = _find_free_port()
    chosen = _pick_port(port, "test")
    assert chosen == port


def test_pick_port_falls_back_when_preferred_busy() -> None:
    busy_port = _find_free_port()
    holder = _bind_and_hold(busy_port)
    try:
        chosen = _pick_port(busy_port, "test")
        # Should bump to a port in the window (not necessarily +1 if other
        # processes claim slots, but always > busy_port and within the window).
        assert chosen != busy_port
        assert busy_port < chosen <= busy_port + 20
    finally:
        holder.close()


def test_pick_port_exits_when_range_exhausted() -> None:
    busy_port = _find_free_port()
    # Mock socket.bind to always raise OSError so the helper exhausts its range.
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_sock.__enter__.return_value = mock_sock
        mock_sock.__exit__.return_value = False
        mock_sock.bind.side_effect = OSError("address in use")
        mock_socket_cls.return_value = mock_sock

        with pytest.raises(typer.Exit) as exc_info:
            _pick_port(busy_port, "test")
        assert exc_info.value.exit_code == 2


# ---------------------------------------------------------------------------
# _check_node_toolchain
# ---------------------------------------------------------------------------


def test_check_node_toolchain_returns_paths_when_present() -> None:
    def fake_which(name: str) -> str | None:
        return {
            "node": "/usr/bin/node",
            "pnpm": "/usr/bin/pnpm",
            "npm": "/usr/bin/npm",
        }.get(name)

    with patch("shutil.which", side_effect=fake_which):
        node_path, pkg_mgr = _check_node_toolchain()
    assert node_path == "/usr/bin/node"
    assert pkg_mgr == "/usr/bin/pnpm"


def test_check_node_toolchain_falls_back_to_npm() -> None:
    def fake_which(name: str) -> str | None:
        return {
            "node": "/usr/bin/node",
            "pnpm": None,
            "npm": "/usr/bin/npm",
        }.get(name)

    with patch("shutil.which", side_effect=fake_which):
        node_path, pkg_mgr = _check_node_toolchain()
    assert node_path == "/usr/bin/node"
    assert pkg_mgr == "/usr/bin/npm"


def test_check_node_toolchain_exits_when_node_missing() -> None:
    with patch("shutil.which", return_value=None), pytest.raises(typer.Exit) as exc_info:
        _check_node_toolchain()
    assert exc_info.value.exit_code == 2


def test_check_node_toolchain_exits_when_pkg_mgr_missing() -> None:
    def fake_which(name: str) -> str | None:
        return {"node": "/usr/bin/node"}.get(name)

    with patch("shutil.which", side_effect=fake_which), pytest.raises(typer.Exit) as exc_info:
        _check_node_toolchain()
    assert exc_info.value.exit_code == 2


# ---------------------------------------------------------------------------
# _wait_for_backend
# ---------------------------------------------------------------------------


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.status = 200
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_wait_for_backend_returns_true_on_200() -> None:
    with patch("urllib.request.urlopen", return_value=_ok_response()):
        assert _wait_for_backend("127.0.0.1", 8000, timeout_s=1.0) is True


def test_wait_for_backend_returns_false_on_timeout() -> None:
    with patch(
        "urllib.request.urlopen",
        side_effect=ConnectionError("nope"),
    ):
        # Use a tight timeout to keep the test fast — the poll loop sleeps in
        # 0.25s increments so 0.4s is enough to give up.
        assert _wait_for_backend("127.0.0.1", 8000, timeout_s=0.4) is False


def test_wait_for_backend_succeeds_after_initial_failures() -> None:
    call_log: list[int] = []

    def flaky_urlopen(*_args: object, **_kwargs: object) -> MagicMock:
        call_log.append(1)
        if len(call_log) < 3:
            raise ConnectionError("not yet")
        return _ok_response()

    with patch("urllib.request.urlopen", side_effect=flaky_urlopen):
        assert _wait_for_backend("127.0.0.1", 8000, timeout_s=2.0) is True
    assert len(call_log) >= 3
