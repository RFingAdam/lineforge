"""MCP server for atlc3.0.

Exposes the analytical and numerical solvers as MCP tools. Long-running
solves use the SEP-1686 Tasks pattern (returns a taskId; client polls
``tasks/get``). Field plots and saved geometries are exposed as resources.

Run with::

    atlc3 mcp-serve

or programmatically::

    from atlc3.mcp_server.server import run_stdio
    run_stdio()
"""

from __future__ import annotations

from atlc3.mcp_server.server import build_server, run_stdio

__all__ = ["build_server", "run_stdio"]
