"""Scheduler — the brain of Orchestra.

Two loops run concurrently:
1. Claim loop: SELECT … FOR UPDATE SKIP LOCKED → dispatch tasks to workers.
2. Reaper loop: find tasks whose lease has expired → requeue them as pending.

The claim loop is the key correctness property: Postgres row-level locking
(FOR UPDATE SKIP LOCKED) ensures exactly-once claiming without a separate
lock service. See ARCHITECTURE.md for the full explanation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone

import asyncpg
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from orchestra.db import settings, async_session_factory
from orchestra.models import Run, RunStatus, Task, TaskStatus
from orchestra.retry import next_run_at
from orchestra.ws import notify_run_event, notify_state_change

logger = logging.getLogger(__name__)


async def reaper_loop() -> None:
    """
    Periodically finds tasks stuck in 'claimed' or 'running' with expired leases
    and requeues them as 'pending'. This is what turns 'the worker died' into
    'the task resumes'. See ARCHITECTURE.md: 'The reaper loop'.
    """
    while True:
        try:
            async with async_session_factory() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(
                    select(Task).where(
                        Task.status.in_([TaskStatus.CLAIMED, TaskStatus.RUNNING]),
                        Task.lease_expires_at < now,
                    )
                )
                expired = result.scalars().all()

                for task in expired:
                    logger.warning(
                        "Reaper: lease expired for task %s (key=%s, worker=%s)",
                        task.id, task.task_key, task.worker_id,
                    )
                    old_status = task.status.value
                    task.status = TaskStatus.PENDING
                    task.lease_id = None
                    task.lease_expires_at = None
                    task.worker_id = None
                    task.current_attempt += 1
                    task.run_at = next_run_at(task.current_attempt)

                    # Notify WS clients of the state transition
                    await notify_state_change(
                        run_id=task.run_id,
                        task_id=task.id,
                        task_key=task.task_key,
                        attempt=task.current_attempt,
                        from_status=old_status,
                        to_status=TaskStatus.PENDING.value,
                    )

                if expired:
                    await db.commit()
                    logger.info("Reaper: requeued %d expired tasks", len(expired))

        except Exception as exc:
            logger.error("Reaper error: %s", exc)

        await asyncio.sleep(settings.reaper_interval_seconds)


async def run_completion_checker() -> None:
    """Check whether any running runs have all tasks completed/failed, and update run status."""
    while True:
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(Run).where(Run.status == RunStatus.RUNNING)
                )
                active_runs = result.scalars().all()

                for run in active_runs:
                    tasks_result = await db.execute(
                        select(Task).where(Task.run_id == run.id)
                    )
                    tasks = tasks_result.scalars().all()

                    if not tasks:
                        continue

                    statuses = {t.status for t in tasks}

                    if any(s == TaskStatus.DEAD_LETTER for s in statuses):
                        run.status = RunStatus.FAILED
                        run.completed_at = datetime.now(timezone.utc)
                        await notify_run_event(run.id, "run.failed")
                        logger.info("Run %s marked FAILED (dead_letter task)", run.id)
                    elif all(s == TaskStatus.SUCCEEDED or s == TaskStatus.SKIPPED for s in statuses):
                        run.status = RunStatus.SUCCEEDED
                        run.completed_at = datetime.now(timezone.utc)
                        await notify_run_event(run.id, "run.completed")
                        logger.info("Run %s SUCCEEDED", run.id)

                if active_runs:
                    await db.commit()

        except Exception as exc:
            logger.error("Run completion checker error: %s", exc)

        await asyncio.sleep(3)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Orchestra scheduler starting")

    async def _run():
        await asyncio.gather(
            reaper_loop(),
            run_completion_checker(),
        )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
