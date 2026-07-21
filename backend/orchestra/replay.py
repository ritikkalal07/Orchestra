"""Deterministic replay debugger.

Reconstructs the exact step-by-step trace of a completed run from
task_attempts + checkpoints without re-executing anything against real systems.
See FEATURES.md: 'Deterministic replay debugger'.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestra.models import Checkpoint, Run, Task, TaskAttempt


async def build_replay_trace(db: AsyncSession, run_id: str) -> dict[str, Any]:
    """
    Return the full deterministic replay trace for a run.

    Shape:
    {
        "run_id": "...",
        "workflow_id": "...",
        "status": "succeeded",
        "steps": [
            {
                "task_key": "fetch",
                "attempt": 1,
                "idempotency_key": "task_abc:1",
                "started_at": "...",
                "ended_at": "...",
                "duration_ms": 142,
                "input": {...},
                "output": {...},
                "error": null,
                "checkpoints": [
                    { "step": "fetched_url", "data": {...}, "recorded_at": "..." }
                ]
            }
        ]
    }
    """
    # Load the run
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        return {}

    # Load all tasks
    result = await db.execute(
        select(Task).where(Task.run_id == run_id).order_by(Task.created_at)
    )
    tasks = result.scalars().all()

    steps = []
    for task in tasks:
        # Load all attempts for this task, ordered by attempt_number
        result = await db.execute(
            select(TaskAttempt)
            .where(TaskAttempt.task_id == task.id)
            .order_by(TaskAttempt.attempt_number)
        )
        attempts = result.scalars().all()

        for attempt in attempts:
            # Load checkpoints for this attempt
            result = await db.execute(
                select(Checkpoint)
                .where(Checkpoint.attempt_id == attempt.id)
                .order_by(Checkpoint.recorded_at)
            )
            checkpoints = result.scalars().all()

            steps.append(
                {
                    "task_key": task.task_key,
                    "task_type": task.task_type,
                    "attempt": attempt.attempt_number,
                    "idempotency_key": attempt.idempotency_key,
                    "worker_id": attempt.worker_id,
                    "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                    "ended_at": attempt.ended_at.isoformat() if attempt.ended_at else None,
                    "duration_ms": attempt.duration_ms,
                    "input": attempt.input_snapshot,
                    "output": attempt.output_snapshot,
                    "error": attempt.error_detail,
                    "checkpoints": [
                        {
                            "step": cp.step,
                            "data": cp.data,
                            "recorded_at": cp.recorded_at.isoformat(),
                        }
                        for cp in checkpoints
                    ],
                }
            )

    return {
        "run_id": run.id,
        "workflow_id": run.workflow_id,
        "workflow_version": run.workflow_version,
        "status": run.status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "steps": steps,
    }


async def diff_runs(
    db: AsyncSession, run_id_a: str, run_id_b: str
) -> dict[str, Any]:
    """
    Produce a structural + output diff between two runs of the same workflow.
    Highlights: tasks added/removed, retry count differences, output changes.
    """
    trace_a = await build_replay_trace(db, run_id_a)
    trace_b = await build_replay_trace(db, run_id_b)

    def tasks_by_key(trace: dict) -> dict[str, list]:
        out: dict[str, list] = {}
        for step in trace.get("steps", []):
            out.setdefault(step["task_key"], []).append(step)
        return out

    a_tasks = tasks_by_key(trace_a)
    b_tasks = tasks_by_key(trace_b)

    all_keys = sorted(set(a_tasks) | set(b_tasks))
    diffs = []

    for key in all_keys:
        in_a = key in a_tasks
        in_b = key in b_tasks

        if in_a and not in_b:
            diffs.append({"task_key": key, "change": "removed"})
        elif in_b and not in_a:
            diffs.append({"task_key": key, "change": "added"})
        else:
            a_attempts = len(a_tasks[key])
            b_attempts = len(b_tasks[key])
            a_out = a_tasks[key][-1].get("output") if a_tasks[key] else None
            b_out = b_tasks[key][-1].get("output") if b_tasks[key] else None

            diff_entry: dict[str, Any] = {"task_key": key, "change": "same"}
            if a_attempts != b_attempts:
                diff_entry["change"] = "retry_count_changed"
                diff_entry["attempts_a"] = a_attempts
                diff_entry["attempts_b"] = b_attempts
            if a_out != b_out:
                diff_entry["output_changed"] = True
                diff_entry["output_a"] = a_out
                diff_entry["output_b"] = b_out
            diffs.append(diff_entry)

    return {
        "run_a": run_id_a,
        "run_b": run_id_b,
        "status_a": trace_a.get("status"),
        "status_b": trace_b.get("status"),
        "diffs": diffs,
    }
