"""WebSocket /ws/progress — push progress updates from long-running solves.

The HTTP solve endpoints in :mod:`app.api_solve` are synchronous (analytical
solves are microseconds). For ``solver='cgp'`` or ``solver='full'`` runs that
take seconds-to-minutes, the API path will (in a future PR) submit the work
to a background task queue and the frontend subscribes to this WebSocket to
get live progress.

C1: ships the endpoint; the message contract is defined and tested via a
manual ``send_progress()`` helper that test fixtures can call.

Wire protocol::

    Server → Client::
        {"type": "progress", "task_id": "...",
         "stage": "rasterizing"|"laplace"|"l_extraction"|"done",
         "frac": 0.0..1.0, "msg": "..."}
        {"type": "result",   "task_id": "...", "result": {...}}
        {"type": "error",    "task_id": "...", "error": "..."}
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


# Per-task subscriber queues — enables fan-out if multiple tabs subscribe to
# the same task id.
_subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
_lock = asyncio.Lock()


async def send_progress(task_id: str, message: dict[str, Any]) -> None:
    """Server-side helper used by background workers to broadcast progress
    to all subscribers of ``task_id``."""
    async with _lock:
        subs = list(_subscribers.get(task_id, []))
    for q in subs:
        await q.put(message)


@router.websocket("/ws/progress/{task_id}")
async def progress_websocket(ws: WebSocket, task_id: str) -> None:
    """Subscribe a frontend client to a task's progress stream."""
    await ws.accept()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    async with _lock:
        _subscribers[task_id].append(queue)
    try:
        while True:
            msg = await queue.get()
            await ws.send_json(msg)
            if msg.get("type") in ("result", "error"):
                # Terminal — close the WebSocket cleanly.
                await ws.close()
                return
    except WebSocketDisconnect:
        return
    finally:
        async with _lock:
            if queue in _subscribers.get(task_id, []):
                _subscribers[task_id].remove(queue)
            if not _subscribers[task_id]:
                _subscribers.pop(task_id, None)
