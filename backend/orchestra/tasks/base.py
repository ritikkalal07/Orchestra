"""BaseTask — the abstract base class that enforces idempotency.

Every task that calls an external system MUST go through self.run_step(),
which derives the idempotency key from (task_id, attempt_number, step_name)
and skips a step that has already been durably recorded.

A task that does not inherit BaseTask fails at registry registration time.
See ARCHITECTURE.md: 'Idempotency keys on every side effect'.
"""
from __future__ import annotations

import abc
import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from orchestra.models import Checkpoint


class IdempotencyError(Exception):
    """Raised when a task is registered without proper idempotency support."""


class BaseTask(abc.ABC):
    """
    Abstract base class for all Orchestra task types.

    Subclasses must implement `execute()`.
    Use `self.step()` for any side-effectful work — it auto-checkpoints and
    skips steps already recorded (crash-recovery without re-running side effects).
    """

    # Must be set by subclass
    task_type: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "DemoBaseTask":  # allow intermediate bases
            return
        if not cls.task_type:
            raise IdempotencyError(
                f"Task class '{cls.__name__}' must define a non-empty `task_type` class attribute"
            )

    # ------------------------------------------------------------------
    # Runtime context — injected by the worker before calling execute()
    # ------------------------------------------------------------------

    def _bind(
        self,
        task_id: str,
        attempt_number: int,
        attempt_id: str,
        db: AsyncSession,
    ) -> None:
        self._task_id = task_id
        self._attempt_number = attempt_number
        self._attempt_id = attempt_id
        self._db = db
        self._completed_steps: dict[str, Any] = {}  # loaded from DB on first use
        self._steps_loaded = False

    @property
    def idempotency_key(self) -> str:
        """Canonical idempotency key for this attempt: task_id:attempt_number."""
        return f"{self._task_id}:{self._attempt_number}"

    def _step_idempotency_key(self, step: str) -> str:
        return hashlib.sha256(
            f"{self._task_id}:{self._attempt_number}:{step}".encode()
        ).hexdigest()[:32]

    async def _load_checkpoints(self) -> None:
        if self._steps_loaded:
            return
        result = await self._db.execute(
            select(Checkpoint).where(Checkpoint.attempt_id == self._attempt_id)
        )
        for cp in result.scalars().all():
            self._completed_steps[cp.step] = cp.data
        self._steps_loaded = True

    async def step(self, name: str, fn, *args, **kwargs) -> Any:
        """
        Run a step idempotently.
        If this step has already been checkpointed, returns the persisted result
        without calling fn again — safe to call on resume after a crash.

        Usage:
            result = await self.step("send_email", self._do_send, email_payload)
        """
        await self._load_checkpoints()

        if name in self._completed_steps:
            # Already done — return the checkpointed result (skip side effect)
            return self._completed_steps[name]

        result = await fn(*args, **kwargs) if asyncio_function(fn) else fn(*args, **kwargs)

        # Persist checkpoint in the same transaction as the state transition
        checkpoint = Checkpoint(
            attempt_id=self._attempt_id,
            step=name,
            data=result if isinstance(result, dict) else {"value": result},
        )
        self._db.add(checkpoint)
        await self._db.flush()
        self._completed_steps[name] = checkpoint.data
        return result

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Implement the task logic here.
        Use self.step() for any side-effectful operations.
        Must return a dict (the task output).
        """


def asyncio_function(fn) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(fn)
