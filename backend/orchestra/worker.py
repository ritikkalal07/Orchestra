"""Worker process — claims tasks, executes them, writes checkpoints.

The worker is a separate, killable process (not a thread inside the API server).
This is intentional: crash-and-resume is only convincing if you can actually
kill -9 the worker and show it recovering. See README.md and ARCHITECTURE.md.

Claiming uses SELECT … FOR UPDATE SKIP LOCKED:
two workers racing for the same task never both claim it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from orchestra.db import async_session_factory, settings
from orchestra.models import Run, RunStatus, Task, TaskAttempt, TaskStatus
from orchestra.retry import next_run_at
from orchestra.tasks.registry import get_task_class
from orchestra.ws import notify_state_change

logger = logging.getLogger(__name__)

WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
_shutdown = asyncio.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim_task(db: AsyncSession) -> Task | None:
    """
    Claim the next available task using SELECT … FOR UPDATE SKIP LOCKED.
    Returns the claimed task, or None if no tasks are available.

    This is the key correctness guarantee: two workers running this query
    concurrently will never both claim the same task — Postgres locks the
    row the first worker is evaluating, the second worker skips locked rows.
    """
    result = await db.execute(
        text("""
            SELECT id FROM tasks
            WHERE status = 'pending' AND run_at <= :now
            ORDER BY priority DESC, run_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """),
        {"now": _now()},
    )
    row = result.fetchone()
    if row is None:
        return None

    # Atomically transition to 'claimed' with a lease
    task_result = await db.execute(select(Task).where(Task.id == row[0]))
    task = task_result.scalar_one()

    lease_id = str(uuid.uuid4())
    lease_expires = _now() + timedelta(seconds=settings.lease_duration_seconds)

    task.status = TaskStatus.CLAIMED
    task.lease_id = lease_id
    task.lease_expires_at = lease_expires
    task.worker_id = WORKER_ID

    await db.commit()
    logger.info("Claimed task %s (key=%s)", task.id, task.task_key)
    return task


async def renew_lease(task_id: str) -> None:
    """Heartbeat: extend the lease so the reaper doesn't reclaim our task."""
    async with async_session_factory() as db:
        await db.execute(
            update(Task)
            .where(Task.id == task_id, Task.worker_id == WORKER_ID)
            .values(
                lease_expires_at=_now() + timedelta(seconds=settings.lease_duration_seconds)
            )
        )
        await db.commit()


async def execute_task(task: Task) -> None:
    """
    Execute a task attempt end-to-end, with lease heartbeating and checkpoint writes.
    """
    async with async_session_factory() as db:
        # Re-fetch under a fresh session
        result = await db.execute(select(Task).where(Task.id == task.id))
        task = result.scalar_one()

        # Create the attempt record
        attempt = TaskAttempt(
            task_id=task.id,
            attempt_number=task.current_attempt,
            idempotency_key=f"{task.id}:{task.current_attempt}",
            worker_id=WORKER_ID,
            started_at=_now(),
            input_snapshot=task.input_data,
        )
        db.add(attempt)
        await db.flush()

        # Transition to running
        old_status = task.status.value
        task.status = TaskStatus.RUNNING
        await db.commit()

        await notify_state_change(
            run_id=task.run_id,
            task_id=task.id,
            task_key=task.task_key,
            attempt=task.current_attempt,
            from_status=old_status,
            to_status=TaskStatus.RUNNING.value,
        )

    # Run the heartbeat in the background while executing
    heartbeat_task = asyncio.create_task(_heartbeat_loop(task.id))

    try:
        task_class = get_task_class(task.task_type)
        instance = task_class()

        # Bind runtime context
        async with async_session_factory() as exec_db:
            instance._bind(task.id, task.current_attempt, attempt.id, exec_db)

            started = _now()
            output = await instance.execute(task.input_data or {})
            duration_ms = int((_now() - started).total_seconds() * 1000)

            # Persist success
            attempt.ended_at = _now()
            attempt.output_snapshot = output
            attempt.duration_ms = duration_ms
            await exec_db.flush()

        async with async_session_factory() as db:
            result = await db.execute(select(Task).where(Task.id == task.id))
            t = result.scalar_one()
            t.status = TaskStatus.SUCCEEDED
            t.output_data = output
            t.lease_id = None
            t.lease_expires_at = None
            await db.commit()

        await notify_state_change(
            run_id=task.run_id,
            task_id=task.id,
            task_key=task.task_key,
            attempt=task.current_attempt,
            from_status=TaskStatus.RUNNING.value,
            to_status=TaskStatus.SUCCEEDED.value,
        )
        logger.info("Task %s succeeded (key=%s)", task.id, task.task_key)

        # Unlock dependent tasks
        await unlock_dependents(task.run_id, task.task_key)

    except Exception as exc:
        logger.exception("Task %s failed: %s", task.id, exc)

        async with async_session_factory() as db:
            result = await db.execute(select(Task).where(Task.id == task.id))
            t = result.scalar_one()

            if t.current_attempt >= t.max_attempts - 1:
                t.status = TaskStatus.DEAD_LETTER
                t.error_detail = str(exc)
                new_status = TaskStatus.DEAD_LETTER.value
            else:
                t.status = TaskStatus.FAILED
                t.error_detail = str(exc)
                new_status = TaskStatus.FAILED.value

            t.lease_id = None
            t.lease_expires_at = None
            await db.commit()

        await notify_state_change(
            run_id=task.run_id,
            task_id=task.id,
            task_key=task.task_key,
            attempt=task.current_attempt,
            from_status=TaskStatus.RUNNING.value,
            to_status=new_status,
        )

        if new_status == TaskStatus.FAILED.value:
            # Schedule a retry
            async with async_session_factory() as db:
                result = await db.execute(select(Task).where(Task.id == task.id))
                t = result.scalar_one()
                t.status = TaskStatus.PENDING
                t.current_attempt += 1
                t.run_at = next_run_at(t.current_attempt)
                await db.commit()

    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def unlock_dependents(run_id: str, completed_key: str) -> None:
    """After a task succeeds, check if any pending tasks now have all deps satisfied."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Task).where(Task.run_id == run_id, Task.status == TaskStatus.PENDING)
        )
        pending_tasks = result.scalars().all()

        result2 = await db.execute(
            select(Task).where(Task.run_id == run_id, Task.status == TaskStatus.SUCCEEDED)
        )
        succeeded = {t.task_key for t in result2.scalars().all()}

        for t in pending_tasks:
            deps = t.depends_on or []
            if all(d in succeeded for d in deps):
                # Merge input: inject output from dependencies
                dep_outputs: dict = {}
                for dep_key in deps:
                    dep_result = await db.execute(
                        select(Task).where(Task.run_id == run_id, Task.task_key == dep_key)
                    )
                    dep_task = dep_result.scalar_one_or_none()
                    if dep_task and dep_task.output_data:
                        dep_outputs[dep_key] = dep_task.output_data

                if dep_outputs:
                    t.input_data = {**(t.input_data or {}), "data": dep_outputs}
                t.run_at = _now()
                logger.info("Task %s unblocked (key=%s)", t.id, t.task_key)

        await db.commit()


async def _heartbeat_loop(task_id: str) -> None:
    while True:
        await asyncio.sleep(settings.heartbeat_interval_seconds)
        try:
            await renew_lease(task_id)
        except Exception as exc:
            logger.warning("Heartbeat failed for task %s: %s", task_id, exc)


async def worker_loop() -> None:
    logger.info("Worker %s started", WORKER_ID)
    while not _shutdown.is_set():
        async with async_session_factory() as db:
            task = await claim_task(db)

        if task:
            asyncio.create_task(execute_task(task))
        else:
            await asyncio.sleep(1)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s (%(process)d): %(message)s",
    )
    logger.info("Orchestra worker starting — worker_id=%s", WORKER_ID)

    loop = asyncio.new_event_loop()

    def handle_signal(sig):
        logger.info("Worker %s: received signal %s, shutting down", WORKER_ID, sig)
        _shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            pass  # Windows

    try:
        loop.run_until_complete(worker_loop())
    finally:
        loop.close()
        logger.info("Worker %s stopped", WORKER_ID)


if __name__ == "__main__":
    main()
