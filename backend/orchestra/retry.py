"""Exponential backoff with full jitter for retry scheduling.

Formula: delay = random(0, min(cap, base * 2^attempt))

Full jitter (not plain exponential backoff) is used deliberately:
it avoids the thundering-herd retry spike that plain exponential
backoff allows when many tasks fail at once (e.g., a downstream API outage).
See ARCHITECTURE.md for the rationale.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone


def compute_backoff(
    attempt: int,
    base_seconds: float = 1.0,
    cap_seconds: float = 300.0,
) -> float:
    """
    Return a jittered backoff delay in seconds.

    Parameters
    ----------
    attempt:
        Zero-indexed attempt count (0 = first retry).
    base_seconds:
        Base delay in seconds.
    cap_seconds:
        Maximum delay ceiling in seconds (default 5 minutes).
    """
    ceiling = min(cap_seconds, base_seconds * (2**attempt))
    return random.uniform(0, ceiling)


def next_run_at(attempt: int, **kwargs) -> datetime:
    """Return the absolute datetime at which the task should next be claimable."""
    delay = compute_backoff(attempt, **kwargs)
    return datetime.now(timezone.utc) + timedelta(seconds=delay)
