from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse


_DEBUG_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("murn_debug_context", default={})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact(value: Any, max_chars: int = 1400) -> Any:
    """Return a JSON-friendly, size-limited representation for the debug UI."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "…"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 24:
                out["…"] = f"{len(value) - 24} more keys"
                break
            out[str(key)] = compact(item, max(180, max_chars // 3))
        return out
    if isinstance(value, (list, tuple)):
        items = [compact(item, max(160, max_chars // 5)) for item in value[:18]]
        if len(value) > 18:
            items.append(f"… {len(value) - 18} more items")
        return items
    return compact(str(value), max_chars)


class DebugBus:
    def __init__(self, max_events: int = 600) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._seq = 0

    def begin(self, source: str, message: str, session_id: str | None = None) -> tuple[str, Token]:
        trace_id = uuid.uuid4().hex[:10]
        token = _DEBUG_CONTEXT.set(
            {
                "trace_id": trace_id,
                "source": source or "unknown",
                "session_id": session_id,
                "started": time.perf_counter(),
            }
        )
        self.emit(
            "request",
            "request received",
            {
                "message": compact(message, 700),
                "session_id": session_id,
            },
        )
        return trace_id, token

    def end_scope(self, token: Token) -> None:
        _DEBUG_CONTEXT.reset(token)

    def context(self) -> dict[str, Any]:
        return dict(_DEBUG_CONTEXT.get())

    def emit(
        self,
        stage: str,
        message: str,
        data: Any | None = None,
        *,
        trace_id: str | None = None,
        source: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        context = self.context()
        self._seq += 1
        event = {
            "seq": self._seq,
            "ts": _utc_now(),
            "trace_id": trace_id or context.get("trace_id") or "system",
            "source": source or context.get("source") or "system",
            "session_id": session_id if session_id is not None else context.get("session_id"),
            "stage": stage,
            "message": message,
            "data": compact(data) if data is not None else None,
        }
        self._events.append(event)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
        return event

    def snapshot(self, limit: int = 120) -> list[dict[str, Any]]:
        limit = max(1, min(600, int(limit)))
        return list(self._events)[-limit:]

    def clear(self) -> None:
        self._events.clear()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=250)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)


debug_bus = DebugBus()


def build_debug_router() -> APIRouter:
    router = APIRouter(prefix="/v1/debug", tags=["debug"])

    @router.get("/snapshot")
    async def snapshot(limit: int = Query(120, ge=1, le=600)):
        return {"events": debug_bus.snapshot(limit), "live": True}

    @router.delete("/events")
    async def clear_events():
        debug_bus.clear()
        return {"ok": True}

    @router.get("/events")
    async def events(backlog: int = Query(0, ge=0, le=300)):
        async def stream():
            queue = debug_bus.subscribe()
            try:
                if backlog:
                    for event in debug_bus.snapshot(backlog):
                        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                        yield f"data: {payload}\n\n"

                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": murn-debug-ping\n\n"
                        continue
                    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                    yield f"data: {payload}\n\n"
            finally:
                debug_bus.unsubscribe(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    return router
