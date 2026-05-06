"""Lightweight async task registry for the MCP server.

Implements the SEP-1686 Tasks lifecycle pattern at the application level: when
an MCP tool kicks off a long-running solve, the tool returns a ``taskId``
immediately, the actual work runs on a background ``asyncio.Task``, and a
``tasks_get`` tool lets the client poll status, retrieve results, and read
field-plot resource URIs.

Phase 2 implements the orchestration around the C/Gp solve. Phase 3 reuses
the same machinery for L/Rs and full-RLGC solves.
"""

from __future__ import annotations

import asyncio
import base64
import io
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

TaskStatus = Literal["submitted", "working", "completed", "failed", "cancelled"]


@dataclass
class Task:
    """One async solve job."""

    id: str
    kind: str
    submitted_at: float
    status: TaskStatus = "submitted"
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    field_plots: dict[str, bytes] = field(default_factory=dict)
    """Per-field PNG bytes, keyed by ``"V"``/``"E"``/``"D"``/``"T"``."""

    def to_status(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "submittedAt": self.submitted_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "error": self.error,
        }


class TaskRegistry:
    """In-memory registry of all running and completed tasks.

    Thread/async-safe via a single asyncio Lock. Tasks are kept around for
    ``keep_alive_seconds`` after completion so clients can retrieve results
    after polling.
    """

    def __init__(self, keep_alive_seconds: float = 3600.0) -> None:
        self._tasks: dict[str, Task] = {}
        self._handles: dict[str, asyncio.Task[Any]] = {}
        self._cleanup_handles: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()
        self.keep_alive_seconds = keep_alive_seconds

    def submit(
        self,
        kind: str,
        coro_factory: Callable[[Task], Any],
    ) -> Task:
        """Register a new task and start its background coroutine."""
        task = Task(
            id=str(uuid.uuid4()),
            kind=kind,
            submitted_at=time.time(),
        )
        self._tasks[task.id] = task

        async def _run() -> None:
            task.status = "working"
            task.started_at = time.time()
            try:
                result = await asyncio.to_thread(coro_factory, task)
                task.result = result
                task.status = "completed"
            except Exception as exc:  # noqa: BLE001
                task.error = f"{type(exc).__name__}: {exc}"
                task.status = "failed"
            finally:
                task.completed_at = time.time()
                # Schedule cleanup after keep-alive window. Hold a strong
                # reference so the cleanup task isn't garbage-collected before
                # it runs (RUF006).
                cleanup_handle = asyncio.create_task(self._cleanup_after(task.id))
                self._cleanup_handles.add(cleanup_handle)
                cleanup_handle.add_done_callback(self._cleanup_handles.discard)

        self._handles[task.id] = asyncio.create_task(_run())
        return task

    async def _cleanup_after(self, task_id: str) -> None:
        await asyncio.sleep(self.keep_alive_seconds)
        async with self._lock:
            self._tasks.pop(task_id, None)
            self._handles.pop(task_id, None)

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        handle = self._handles.get(task_id)
        if handle is None:
            return False
        handle.cancel()
        t = self._tasks.get(task_id)
        if t is not None and t.status in {"submitted", "working"}:
            t.status = "cancelled"
            t.completed_at = time.time()
        return True


def encode_png(image_bytes: bytes) -> str:
    """Encode PNG bytes as base64 for embedding in JSON tool responses."""
    return base64.b64encode(image_bytes).decode("ascii")


def png_to_bytes(image: Any) -> bytes:
    """Convert a PIL Image to PNG bytes."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


__all__ = ["Task", "TaskRegistry", "TaskStatus", "encode_png", "png_to_bytes"]
