"""DAG validation: schema checking, cycle detection, task-type existence."""
from __future__ import annotations

from typing import Any


class DAGValidationError(Exception):
    pass


def validate_workflow_definition(definition: dict[str, Any]) -> None:
    """
    Validate a workflow definition dict.

    Expected shape:
    {
        "tasks": {
            "fetch": { "type": "http_fetch", "depends_on": [], "max_attempts": 3, "input": {...} },
            "transform": { "type": "json_transform", "depends_on": ["fetch"], "max_attempts": 3 },
            "notify": { "type": "mock_notify", "depends_on": ["transform"], "max_attempts": 3 }
        }
    }
    """
    from orchestra.tasks.registry import task_registry

    if not isinstance(definition, dict):
        raise DAGValidationError("Workflow definition must be a JSON object")

    tasks = definition.get("tasks")
    if not tasks or not isinstance(tasks, dict):
        raise DAGValidationError("Workflow definition must have a non-empty 'tasks' object")

    # Validate each task node
    for key, task_def in tasks.items():
        if not isinstance(task_def, dict):
            raise DAGValidationError(f"Task '{key}' must be an object")

        task_type = task_def.get("type")
        if not task_type:
            raise DAGValidationError(f"Task '{key}' must have a 'type' field")

        if task_type not in task_registry:
            raise DAGValidationError(
                f"Task '{key}' references unknown type '{task_type}'. "
                f"Registered types: {sorted(task_registry.keys())}"
            )

        max_attempts = task_def.get("max_attempts")
        if max_attempts is None:
            raise DAGValidationError(
                f"Task '{key}' must declare 'max_attempts' (no unlimited retries allowed)"
            )
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise DAGValidationError(
                f"Task '{key}': max_attempts must be a positive integer"
            )

        depends_on = task_def.get("depends_on", [])
        if not isinstance(depends_on, list):
            raise DAGValidationError(f"Task '{key}': depends_on must be a list")

        for dep in depends_on:
            if dep not in tasks:
                raise DAGValidationError(
                    f"Task '{key}' depends on '{dep}', which is not defined in this workflow"
                )

    # Cycle detection via topological sort (Kahn's algorithm)
    in_degree: dict[str, int] = {k: 0 for k in tasks}
    adjacency: dict[str, list[str]] = {k: [] for k in tasks}

    for key, task_def in tasks.items():
        for dep in task_def.get("depends_on", []):
            adjacency[dep].append(key)
            in_degree[key] += 1

    queue = [k for k, d in in_degree.items() if d == 0]
    visited = 0

    while queue:
        node = queue.pop()
        visited += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(tasks):
        raise DAGValidationError(
            "Workflow definition contains a cycle. A workflow must be a valid DAG."
        )


def topological_order(tasks: dict[str, Any]) -> list[str]:
    """Return task keys in topological execution order."""
    in_degree: dict[str, int] = {k: 0 for k in tasks}
    adjacency: dict[str, list[str]] = {k: [] for k in tasks}

    for key, task_def in tasks.items():
        for dep in task_def.get("depends_on", []):
            adjacency[dep].append(key)
            in_degree[key] += 1

    queue = [k for k, d in in_degree.items() if d == 0]
    order = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return order


def get_dag_depth(tasks: dict[str, Any]) -> dict[str, int]:
    """Return the DAG depth (longest path from root) for each task key. Used for Y-axis placement in Score View."""
    depths: dict[str, int] = {}

    def depth(key: str) -> int:
        if key in depths:
            return depths[key]
        deps = tasks[key].get("depends_on", [])
        if not deps:
            depths[key] = 0
        else:
            depths[key] = max(depth(d) for d in deps) + 1
        return depths[key]

    for k in tasks:
        depth(k)

    return depths
