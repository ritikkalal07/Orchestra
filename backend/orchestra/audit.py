"""Tamper-evident hash-chain audit log.

Each row's hash = SHA-256(prev_hash + entity_type + entity_id + action + at + metadata).
This lightweight hash chain lets anyone verify that the log wasn't edited after the fact
without needing distributed consensus. See FEATURES.md and SECURITY.md.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from orchestra.models import AuditLog


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _compute_hash(
    prev_hash: str | None,
    seq: int,
    entity_type: str,
    entity_id: str,
    action: str,
    at: datetime,
    metadata: dict | None,
) -> str:
    payload = json.dumps(
        {
            "prev_hash": prev_hash or "",
            "seq": seq,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "at": at.isoformat(),
            "metadata": metadata or {},
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


async def append_audit(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    action: str,
    from_status: str | None = None,
    to_status: str | None = None,
    actor: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """
    Append a new entry to the tamper-evident audit chain.
    Reads the last row to get prev_hash and seq, then inserts the new row.
    """
    # Get last row in chain
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
    )
    last = result.scalar_one_or_none()

    seq = (last.seq + 1) if last else 1
    prev_hash = last.row_hash if last else None
    at = _now()

    row_hash = _compute_hash(prev_hash, seq, entity_type, entity_id, action, at, metadata)

    entry = AuditLog(
        seq=seq,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        metadata=metadata,
        at=at,
        row_hash=row_hash,
        prev_hash=prev_hash,
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_chain(db: AsyncSession) -> tuple[bool, str]:
    """
    Walk the full audit chain and verify each row's hash.
    Returns (is_valid, detail_message).
    """
    result = await db.execute(select(AuditLog).order_by(AuditLog.seq.asc()))
    rows = result.scalars().all()

    prev_hash = None
    for row in rows:
        expected = _compute_hash(
            prev_hash, row.seq, row.entity_type, row.entity_id,
            row.action, row.at, row.metadata,
        )
        if expected != row.row_hash:
            return False, f"Hash mismatch at seq={row.seq} (id={row.id})"
        prev_hash = row.row_hash

    return True, f"Chain valid — {len(rows)} entries verified"
