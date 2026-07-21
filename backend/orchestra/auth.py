"""JWT auth, refresh token rotation, and role enforcement."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from orchestra.db import get_db, settings
from orchestra.models import RefreshToken, UserRole

bearer_scheme = HTTPBearer()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def create_access_token(user_id: str, role: UserRole) -> str:
    expire = _now() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "role": role.value, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token() -> str:
    """Generate a cryptographically random opaque refresh token."""
    return secrets.token_urlsafe(48)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def store_refresh_token(
    db: AsyncSession, token: str, user_id: str, role: UserRole
) -> None:
    expire = _now() + timedelta(days=settings.refresh_token_expire_days)
    record = RefreshToken(
        token_hash=_hash_token(token),
        user_id=user_id,
        role=role.value,
        expires_at=expire,
    )
    db.add(record)
    await db.commit()


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


async def rotate_refresh_token(
    db: AsyncSession, old_token: str
) -> tuple[str, str, str]:
    """
    Exchange old_token → (new_access_token, new_refresh_token, user_id).
    Reuse detection: if old token was already consumed, revoke the whole session.
    """
    token_hash = _hash_token(old_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()

    if record is None or record.revoked:
        raise HTTPException(status_code=401, detail="Refresh token not found or revoked")

    if record.used:
        # Token reuse — possible theft, revoke entire session
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == record.user_id)
            .values(revoked=True)
        )
        await db.commit()
        raise HTTPException(
            status_code=401,
            detail="Refresh token reuse detected — session revoked",
        )

    if record.expires_at < _now():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Mark old token as used
    record.used = True
    await db.flush()

    role = UserRole(record.role)
    new_refresh = create_refresh_token()
    await store_refresh_token(db, new_refresh, record.user_id, role)

    access = create_access_token(record.user_id, role)
    return access, new_refresh, record.user_id


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> dict:
    return decode_access_token(credentials.credentials)


def require_role(*roles: UserRole):
    async def checker(
        user: Annotated[dict, Depends(get_current_user)],
    ) -> dict:
        if UserRole(user["role"]) not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {[r.value for r in roles]}",
            )
        return user

    return checker


require_viewer = require_role(UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN)
require_operator = require_role(UserRole.OPERATOR, UserRole.ADMIN)
require_admin = require_role(UserRole.ADMIN)
