"""WebSocket gateway — Postgres LISTEN/NOTIFY fan-out to Score View clients.

Postgres fires a NOTIFY on the `task_state_changes` channel whenever
a task row transitions state (via a DB trigger defined in the migration).
This gateway subscribes once per process and fans the events to all
connected WebSocket clients — no polling, truly live.
See ARCHITECTURE.md: 'Live updates without polling'.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

import asyncpg
from fastapi import WebSocket

from orchestra.db import settings

logger = logging.getLogger(__name__)

# run_id → set of connected WebSocket objects
_subscribers: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


async def subscribe(run_id: str, ws: WebSocket) -> None:
    async with _lock:
        _subscribers[run_id].add(ws)


async def unsubscribe(run_id: str, ws: WebSocket) -> None:
    async with _lock:
        _subscribers[run_id].discard(ws)
        if not _subscribers[run_id]:
            del _subscribers[run_id]


async def _broadcast(run_id: str, event: dict[str, Any]) -> None:
    message = json.dumps(event)
    dead: list[WebSocket] = []
    async with _lock:
        sockets = set(_subscribers.get(run_id, set()))

    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        await unsubscribe(run_id, ws)


async def notify_state_change(
    run_id: str,
    task_id: str,
    task_key: str,
    attempt: int,
    from_status: str,
    to_status: str,
) -> None:
    """Called by the scheduler/worker to push a state transition to WS clients."""
    from datetime import datetime, timezone

    event = {
        "event": "task.state_changed",
        "run_id": run_id,
        "task_id": task_id,
        "task_key": task_key,
        "attempt": attempt,
        "from": from_status,
        "to": to_status,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await _broadcast(run_id, event)


async def notify_run_event(run_id: str, event_type: str, data: dict | None = None) -> None:
    """Push a run-level event (started, completed, failed, paused)."""
    from datetime import datetime, timezone

    event = {
        "event": event_type,
        "run_id": run_id,
        "at": datetime.now(timezone.utc).isoformat(),
        **(data or {}),
    }
    await _broadcast(run_id, event)


async def listen_postgres(dsn: str) -> None:
    """
    Background coroutine: connect to Postgres and LISTEN on task_state_changes.
    On each NOTIFY, parse the payload and fan out to WS clients.
    Reconnects on failure with exponential backoff.
    """
    delay = 1.0
    while True:
        try:
            conn = await asyncpg.connect(dsn)
            logger.info("WS gateway: LISTEN on task_state_changes")

            async def on_notify(conn, pid, channel, payload):
                try:
                    data = json.loads(payload)
                    run_id = data.get("run_id")
                    if run_id:
                        await _broadcast(run_id, data)
                except Exception as exc:
                    logger.warning("WS gateway: bad payload: %s", exc)

            await conn.add_listener("task_state_changes", on_notify)
            delay = 1.0
            # Keep alive until connection drops
            while not conn.is_closed():
                await asyncio.sleep(5)
            await conn.remove_listener("task_state_changes", on_notify)
        except Exception as exc:
            logger.error("WS gateway disconnected: %s — reconnecting in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
