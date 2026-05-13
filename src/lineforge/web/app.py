"""FastAPI app entry point — wires up REST, WebSockets, and CORS."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env if present so ANTHROPIC_API_KEY etc. flow to the agent without
# needing the user to export them by hand. Silent no-op if python-dotenv
# isn't installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _chat_available() -> bool:
    """Best-effort: do we have credentials to drive the real agent?

    Returns True if any of:
      - ANTHROPIC_API_KEY / CLAUDE_API_KEY in env
      - ATLC3_GUI_CHAT_STUB=0 AND a `claude` CLI on PATH (subscription flow)
    """
    if os.environ.get("ATLC3_GUI_CHAT_STUB") == "1":
        return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"):
        return True
    if shutil.which("claude"):
        try:
            r = subprocess.run(["claude", "--version"], capture_output=True, timeout=2, check=False)
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return False


from lineforge.web import __version__
from lineforge.web.api_field_plot import router as field_plot_router
from lineforge.web.api_geometries import router as geometries_router
from lineforge.web.api_materials import router as materials_router
from lineforge.web.api_solve import router as solve_router
from lineforge.web.api_usermap import router as usermap_router
from lineforge.web.state import get_state, reset_state
from lineforge.web.ws_chat import router as chat_router
from lineforge.web.ws_progress import router as progress_router

app = FastAPI(
    title="atlc3-gui-backend",
    version=__version__,
    description="FastAPI backend for the atlc3 web GUI.",
)

# CORS: open during local dev. The GUI is intended for localhost-only use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(geometries_router)
app.include_router(solve_router)
app.include_router(field_plot_router)
app.include_router(usermap_router)
app.include_router(materials_router)
app.include_router(chat_router)
app.include_router(progress_router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness probe + chat-availability flag."""
    import lineforge

    return {
        "status": "ok",
        "atlc3_gui_version": __version__,
        "atlc3_version": lineforge.__version__,
        "chat_available": _chat_available(),
    }


@app.get("/api/state")
async def state_get() -> Any:
    """Snapshot the current GUI state."""
    snap = await get_state()
    return snap.model_dump()


@app.post("/api/state/reset")
async def state_reset() -> dict[str, str]:
    """Reset the GUI session to a fresh state."""
    await reset_state()
    return {"status": "reset"}
