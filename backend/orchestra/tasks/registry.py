"""Closed task registry — the security boundary.

Only task types explicitly registered here can be referenced in workflow definitions.
A workflow definition cannot ship arbitrary executable logic.
See SECURITY.md: 'Task types are a closed, code-reviewed registry'.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from orchestra.tasks.base import BaseTask

# The closed registry — map of task_type string → task class
task_registry: dict[str, Type["BaseTask"]] = {}


def register(cls: Type["BaseTask"]) -> Type["BaseTask"]:
    """
    Decorator to register a task class in the closed registry.
    Fails at import time if the class doesn't have a task_type.
    """
    from orchestra.tasks.base import IdempotencyError

    if not cls.task_type:
        raise IdempotencyError(
            f"Cannot register '{cls.__name__}': task_type is empty"
        )
    task_registry[cls.task_type] = cls
    return cls


def get_task_class(task_type: str) -> Type["BaseTask"]:
    """Retrieve a task class by type name, or raise if not registered."""
    if task_type not in task_registry:
        raise KeyError(
            f"Unknown task type '{task_type}'. "
            f"Registered: {sorted(task_registry.keys())}"
        )
    return task_registry[task_type]


# Import demo tasks to trigger their @register decorators
from orchestra.tasks import demo_tasks as _demo_tasks  # noqa: F401, E402
