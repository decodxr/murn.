from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
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
    """Cross-process debug event bus backed by a tiny shared SQLite database."""

    def __init__(self, path: Path | None = None, max_events: int = 1200) -> None:
        data_dir = Path(os.getenv("MURN_DATA_DIR", ".murn")).expanduser()
        self.path = path or (data_dir / "debug_events.db")
        self.max_events = max(300, int(max_events))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS debug_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    session_id TEXT,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_debug_events_trace ON debug_events(trace_id, seq)"
            )

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

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
        data = None
        if row["data_json"]:
            try:
                data = json.loads(row["data_json"])
            except json.JSONDecodeError:
                data = row["data_json"]
        return {
            "seq": row["seq"],
            "ts": row["ts"],
            "trace_id": row["trace_id"],
            "source": row["source"],
            "session_id": row["session_id"],
            "stage": row["stage"],
            "message": row["message"],
            "data": data,
        }

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
        timestamp = _utc_now()
        trace = trace_id or context.get("trace_id") or "system"
        origin = source or context.get("source") or "system"
        session = session_id if session_id is not None else context.get("session_id")
        compact_data = compact(data) if data is not None else None
        data_json = json.dumps(compact_data, ensure_ascii=False) if compact_data is not None else None

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO debug_events(ts, trace_id, source, session_id, stage, message, data_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (timestamp, trace, origin, session, stage, message, data_json),
            )
            seq = int(cursor.lastrowid)
            # Keep the database tiny even if debug is left enabled for weeks.
            connection.execute(
                "DELETE FROM debug_events WHERE seq <= (SELECT COALESCE(MAX(seq), 0) - ? FROM debug_events)",
                (self.max_events,),
            )

        return {
            "seq": seq,
            "ts": timestamp,
            "trace_id": trace,
            "source": origin,
            "session_id": session,
            "stage": stage,
            "message": message,
            "data": compact_data,
        }

    def snapshot(self, limit: int = 120) -> list[dict[str, Any]]:
        limit = max(1, min(600, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM debug_events ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_event(row) for row in reversed(rows)]

    def events_after(self, seq: int, limit: int = 120) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM debug_events WHERE seq > ? ORDER BY seq ASC LIMIT ?",
                (max(0, int(seq)), max(1, min(300, int(limit)))),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def latest_seq(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM debug_events").fetchone()
        return int(row["seq"] if row else 0)

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM debug_events")


debug_bus = DebugBus()


def build_debug_router() -> APIRouter:
    router = APIRouter(prefix="/v1/debug", tags=["debug"])

    @router.get("/snapshot")
    async def snapshot(limit: int = Query(120, ge=1, le=600)):
        return {
            "events": await asyncio.to_thread(debug_bus.snapshot, limit),
            "live": True,
            "shared": True,
        }

    @router.delete("/events")
    async def clear_events():
        await asyncio.to_thread(debug_bus.clear)
        return {"ok": True}

    @router.get("/events")
    async def events(backlog: int = Query(0, ge=0, le=300)):
        async def stream():
            if backlog:
                initial = await asyncio.to_thread(debug_bus.snapshot, backlog)
                last_seq = initial[-1]["seq"] if initial else await asyncio.to_thread(debug_bus.latest_seq)
                for event in initial:
                    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                    yield f"data: {payload}\n\n"
            else:
                last_seq = await asyncio.to_thread(debug_bus.latest_seq)

            ping_at = time.monotonic()
            while True:
                events_now = await asyncio.to_thread(debug_bus.events_after, last_seq, 120)
                if events_now:
                    for event in events_now:
                        last_seq = max(last_seq, int(event["seq"]))
                        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                        yield f"data: {payload}\n\n"
                    ping_at = time.monotonic()
                elif time.monotonic() - ping_at >= 15:
                    yield ": murn-debug-ping\n\n"
                    ping_at = time.monotonic()
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    return router
