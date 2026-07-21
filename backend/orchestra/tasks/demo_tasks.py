"""Demo tasks: http_fetch, json_transform, mock_notify.

These implement the 'fetch → transform → notify' demo DAG.
Each demonstrates crash-safe execution via self.step() checkpoints.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from orchestra.tasks.base import BaseTask
from orchestra.tasks.registry import register


@register
class HttpFetchTask(BaseTask):
    """Fetch a URL and return the response body.

    Demonstrates: checkpointing the fetched content so a crash-resume
    doesn't re-issue the HTTP request.
    """

    task_type = "http_fetch"

    async def _do_fetch(self, url: str, headers: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            try:
                body = response.json()
            except Exception:
                body = response.text
            return {
                "status_code": response.status_code,
                "body": body,
                "url": url,
            }

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        url = input_data.get("url", "https://httpbin.org/get")
        headers = input_data.get("headers", {})

        # self.step() ensures this HTTP call is made exactly once,
        # even if the worker crashes mid-execution and is restarted.
        result = await self.step("fetch_url", self._do_fetch, url, headers)
        return result


@register
class JsonTransformTask(BaseTask):
    """Apply a simple JSON transformation: extract a field, reshape, or filter.

    Demonstrates: a CPU-bound step that is also checkpointed,
    so even pure computation is safe to resume.
    """

    task_type = "json_transform"

    def _do_transform(self, data: Any, transform_spec: dict) -> dict:
        """
        Simple transform: extract keys, rename fields, or wrap in a new shape.
        spec = { "extract_keys": [...], "rename": {"old": "new"}, "wrap_key": "result" }
        """
        if isinstance(data, dict):
            payload = data.get("body", data)
        else:
            payload = {"raw": data}

        extract_keys = transform_spec.get("extract_keys")
        if extract_keys and isinstance(payload, dict):
            payload = {k: payload[k] for k in extract_keys if k in payload}

        rename = transform_spec.get("rename", {})
        if rename and isinstance(payload, dict):
            payload = {rename.get(k, k): v for k, v in payload.items()}

        wrap_key = transform_spec.get("wrap_key")
        if wrap_key:
            payload = {wrap_key: payload}

        return {"transformed": payload}

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        data = input_data.get("data") or input_data
        transform_spec = input_data.get("transform_spec", {})

        result = await self.step(
            "transform", lambda: self._do_transform(data, transform_spec)
        )
        return result


@register
class MockNotifyTask(BaseTask):
    """Mock email/webhook notification — logs the notification, doesn't actually send.

    In a real system, this would call SendGrid / Slack / PagerDuty.
    The idempotency_key passed to the external service prevents duplicate sends
    on retry: the external system sees the same key and deduplicates.
    """

    task_type = "mock_notify"

    async def _do_notify(self, recipient: str, subject: str, body: str, idem_key: str) -> dict:
        # In production: await sendgrid_client.send(to=recipient, subject=subject,
        #     body=body, idempotency_key=idem_key)
        # For the demo: simulate a short async delay and log.
        await asyncio.sleep(0.5)
        return {
            "sent": True,
            "recipient": recipient,
            "subject": subject,
            "idempotency_key": idem_key,
            "message": f"[MOCK] Notification sent to {recipient}",
        }

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        recipient = input_data.get("recipient", "demo@orchestra.dev")
        subject = input_data.get("subject", "Orchestra Run Complete")
        body = input_data.get("body", str(input_data.get("data", "Run complete")))

        # idempotency_key is derived from (task_id, attempt_number) — safe to retry
        result = await self.step(
            "send_notification",
            self._do_notify,
            recipient,
            subject,
            body,
            self.idempotency_key,
        )
        return result


@register
class SleepTask(BaseTask):
    """Long-sleep task — useful for demonstrating crash-recovery live in demos.

    Sleep for `duration_seconds`, writing checkpoints at each second elapsed.
    Kill the worker mid-sleep, restart it: it resumes from the last checkpoint,
    not from second zero.
    """

    task_type = "sleep"

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        duration = int(input_data.get("duration_seconds", 10))
        completed = []

        # Load how far we got before any previous crash
        await self._load_checkpoints()

        for i in range(1, duration + 1):
            step_name = f"tick_{i}"
            if step_name in self._completed_steps:
                completed.append(i)
                continue  # already done before crash — skip

            await asyncio.sleep(1)

            await self.step(step_name, lambda sec=i: {"elapsed": sec})
            completed.append(i)

        return {"slept_seconds": duration, "completed_ticks": completed}
