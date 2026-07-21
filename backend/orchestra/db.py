"""Database engine, session factory, and settings."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://orchestra:orchestra@localhost:5432/orchestra"
    database_url_sync: str = "postgresql+psycopg2://orchestra:orchestra@localhost:5432/orchestra"
    jwt_secret: str = "change-me-to-a-long-random-string-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    environment: str = "development"
    worker_id: str = "worker-1"
    lease_duration_seconds: int = 30
    heartbeat_interval_seconds: int = 10
    reaper_interval_seconds: int = 5
    claim_batch_size: int = 1
    max_task_payload_bytes: int = 262144
    max_retry_attempts_default: int = 10
    rehearsal_mode_enabled: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Configure engine kwargs for serverless environments
engine_kwargs: dict = {
    "echo": settings.environment == "development",
    "pool_pre_ping": True,
}

# In Vercel / serverless environment, use NullPool or smaller pool size
if os.environ.get("VERCEL") or settings.environment == "production":
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10

engine = create_async_engine(settings.database_url, **engine_kwargs)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency that yields a DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
