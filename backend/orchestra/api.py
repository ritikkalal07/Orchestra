"""FastAPI application — REST + WebSocket API for Orchestra.

All routes from API.md are implemented here.
Auth is JWT-based; roles are enforced server-side on every request.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from orchestra.audit import append_audit, verify_chain
from orchestra.auth import (
    UserRole,
    create_access_token,
    create_refresh_token,
    get_current_user,
    require_admin,
    require_operator,
    require_viewer,
    rotate_refresh_token,
    store_refresh_token,
)
from orchestra.dag import get_dag_depth, topological_order, validate_workflow_definition
from orchestra.db import async_session_factory, get_db, settings
from orchestra.models import (
    AuditLog,
    Checkpoint,
    Run,
    RunStatus,
    Task,
    TaskAttempt,
    TaskStatus,
    Workflow,
    WorkflowVersion,
)
from orchestra.replay import build_replay_trace, diff_runs
from orchestra.ws import listen_postgres, notify_run_event, notify_state_change, subscribe, unsubscribe

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Orchestra",
    description="Durable workflow orchestrator API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    tb = traceback.format_exc()
    logger.error("Unhandled exception: %s\n%s", exc, tb)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal Server Error: {str(exc)}",
            "traceback": tb,
            "message": str(exc),
        }
    )


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup() -> None:
    # Programmatic Alembic database migrations on startup for serverless/production
    # Runs in a separate thread so Alembic's inner asyncio.run call does not conflict with the active loop
    import os
    if settings.environment == "production" or os.environ.get("VERCEL"):
        logger.info("Orchestra environment is production or serverless. Running database migrations...")
        
        from alembic.config import Config
        from alembic import command
        from pathlib import Path
        
        def run_migrations():
            try:
                base_dir = Path(__file__).resolve().parent.parent
                alembic_ini_path = base_dir / "alembic.ini"
                script_location = base_dir / "alembic"
                
                alembic_cfg = Config(str(alembic_ini_path))
                alembic_cfg.set_main_option("script_location", str(script_location))
                alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
                
                command.upgrade(alembic_cfg, "head")
                logger.info("Database migrations applied successfully.")
            except Exception as e:
                logger.error("Failed to run database migrations: %s", e, exc_info=True)
                
        await asyncio.to_thread(run_migrations)

    # Start the Postgres LISTEN/NOTIFY gateway in the background (only if not on Vercel)
    if not os.environ.get("VERCEL"):
        pg_dsn = settings.database_url.replace("+asyncpg", "")
        asyncio.create_task(listen_postgres(pg_dsn))
    logger.info("Orchestra API started")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    definition: dict[str, Any]


class WorkflowOut(BaseModel):
    id: str
    name: str
    description: str | None
    definition: dict
    current_version: int
    created_at: datetime


class TriggerRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class RunOut(BaseModel):
    id: str
    workflow_id: str
    workflow_version: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class TaskOut(BaseModel):
    id: str
    task_key: str
    task_type: str
    status: str
    current_attempt: int
    max_attempts: int
    depends_on: list | None
    input_data: dict | None
    output_data: dict | None
    error_detail: str | None


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

auth_router = APIRouter(prefix="/auth", tags=["auth"])


# Demo: hardcoded users. In production replace with DB lookup.
_DEMO_USERS = {
    "admin": ("admin123", UserRole.ADMIN),
    "operator": ("op123", UserRole.OPERATOR),
    "viewer": ("view123", UserRole.VIEWER),
}


@auth_router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user_entry = _DEMO_USERS.get(body.username)
    if not user_entry or user_entry[0] != body.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    role = user_entry[1]
    access = create_access_token(body.username, role)
    refresh = create_refresh_token()
    await store_refresh_token(db, refresh, body.username, role)

    return LoginResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/refresh", response_model=LoginResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    access, new_refresh, user_id = await rotate_refresh_token(db, body.refresh_token)
    return LoginResponse(access_token=access, refresh_token=new_refresh)


# ---------------------------------------------------------------------------
# Workflow routes
# ---------------------------------------------------------------------------

wf_router = APIRouter(prefix="/workflows", tags=["workflows"])


async def seed_demo_workflow_if_empty(db: AsyncSession) -> None:
    result = await db.execute(select(func.count(Workflow.id)))
    count = result.scalar()
    if count == 0:
        demo_def = {
            "tasks": {
                "fetch": {
                    "type": "http_fetch",
                    "depends_on": [],
                    "max_attempts": 3,
                    "input": {"url": "https://httpbin.org/get"}
                },
                "transform": {
                    "type": "json_transform",
                    "depends_on": ["fetch"],
                    "max_attempts": 3,
                    "input": {"transform_spec": {"wrap_key": "processed_payload"}}
                },
                "notify": {
                    "type": "mock_notify",
                    "depends_on": ["transform"],
                    "max_attempts": 3,
                    "input": {"recipient": "demo@orchestra.dev", "subject": "Orchestra Pipeline Execution Finished"}
                }
            }
        }
        wf = Workflow(
            id=str(uuid.uuid4()),
            name="Data Pipeline Demo (fetch → transform → notify)",
            description="Default demo workflow showcasing HTTP fetch, JSON transform, and mock notification",
            definition=demo_def,
            current_version=1,
        )
        db.add(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version=1,
            definition=demo_def,
            published_by="system",
        )
        db.add(version)
        await db.commit()


@wf_router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    user=Depends(require_viewer), db: AsyncSession = Depends(get_db)
):
    await seed_demo_workflow_if_empty(db)
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    return [
        WorkflowOut(
            id=w.id, name=w.name, description=w.description,
            definition=w.definition, current_version=w.current_version,
            created_at=w.created_at,
        )
        for w in result.scalars().all()
    ]


@wf_router.post("", response_model=WorkflowOut, status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Validate DAG before storage — cycles rejected here, not at runtime
    try:
        validate_workflow_definition(body.definition)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    wf = Workflow(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        definition=body.definition,
        current_version=1,
    )
    db.add(wf)
    version = WorkflowVersion(
        workflow_id=wf.id,
        version=1,
        definition=body.definition,
        published_by=user["sub"],
    )
    db.add(version)
    await db.flush()
    await append_audit(db, "workflow", wf.id, "created", actor=user["sub"])
    await db.commit()

    return WorkflowOut(
        id=wf.id, name=wf.name, description=wf.description,
        definition=wf.definition, current_version=wf.current_version,
        created_at=wf.created_at,
    )


@wf_router.get("/{wf_id}", response_model=WorkflowOut)
async def get_workflow(
    wf_id: str, user=Depends(require_viewer), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Workflow).where(Workflow.id == wf_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowOut(
        id=wf.id, name=wf.name, description=wf.description,
        definition=wf.definition, current_version=wf.current_version,
        created_at=wf.created_at,
    )


@wf_router.post("/{wf_id}/versions", status_code=201)
async def publish_version(
    wf_id: str,
    body: WorkflowCreate,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workflow).where(Workflow.id == wf_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        validate_workflow_definition(body.definition)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    new_version = wf.current_version + 1
    wf.current_version = new_version
    wf.definition = body.definition

    version = WorkflowVersion(
        workflow_id=wf_id,
        version=new_version,
        definition=body.definition,
        published_by=user["sub"],
    )
    db.add(version)
    await append_audit(db, "workflow", wf_id, "version_published", actor=user["sub"],
                       metadata={"version": new_version})
    await db.commit()

    return {"workflow_id": wf_id, "version": new_version}


# ---------------------------------------------------------------------------
# Run routes
# ---------------------------------------------------------------------------

runs_router = APIRouter(prefix="/runs", tags=["runs"])


@runs_router.get("")
async def list_runs(
    workflow_id: str | None = None,
    user=Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """List runs, optionally filtered by workflow_id."""
    query = select(Run).order_by(Run.created_at.desc()).limit(50)
    if workflow_id:
        query = query.where(Run.workflow_id == workflow_id)
    result = await db.execute(query)
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "workflow_id": r.workflow_id,
            "workflow_version": r.workflow_version,
            "status": r.status.value,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "created_at": r.created_at,
        }
        for r in runs
    ]


@wf_router.post("/{wf_id}/runs", status_code=201)
async def trigger_run(
    wf_id: str,
    body: TriggerRunRequest,
    user=Depends(require_operator),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workflow).where(Workflow.id == wf_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    now = datetime.now(timezone.utc)
    run = Run(
        id=str(uuid.uuid4()),
        workflow_id=wf_id,
        workflow_version=wf.current_version,
        status=RunStatus.RUNNING,
        trigger_input=body.input,
        triggered_by=user["sub"],
        started_at=now,
    )
    db.add(run)
    await db.flush()

    # Create task rows from the workflow definition
    task_defs = wf.definition.get("tasks", {})
    order = topological_order(task_defs)

    for task_key in order:
        task_def = task_defs[task_key]
        task = Task(
            id=str(uuid.uuid4()),
            run_id=run.id,
            task_key=task_key,
            task_type=task_def["type"],
            max_attempts=task_def.get("max_attempts", 3),
            depends_on=task_def.get("depends_on", []),
            input_data={**task_def.get("input", {}), **body.input},
            run_at=now,
        )
        # Only tasks with no dependencies are initially runnable
        if task_def.get("depends_on"):
            task.status = TaskStatus.PENDING
            # Set run_at far future so they're not claimed until deps complete
            from datetime import timedelta
            task.run_at = now + timedelta(days=3650)
        db.add(task)

    await append_audit(db, "run", run.id, "triggered", actor=user["sub"],
                       to_status=RunStatus.RUNNING.value)
    await db.commit()

    await notify_run_event(run.id, "run.started", {"workflow_id": wf_id})

    # Trigger immediate task execution pass (works on local & serverless/Vercel)
    asyncio.create_task(process_tasks_pass())

    return {"run_id": run.id, "status": run.status.value}


async def process_tasks_pass() -> int:
    """Claim and execute available tasks in sequence until no more claimable tasks remain."""
    from orchestra.worker import claim_task, execute_task
    processed = 0
    while True:
        async with async_session_factory() as db:
            task = await claim_task(db)
        if not task:
            break
        await execute_task(task)
        processed += 1
    return processed



@runs_router.get("/{run_id}")
async def get_run(
    run_id: str, user=Depends(require_viewer), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    tasks_result = await db.execute(select(Task).where(Task.run_id == run_id))
    tasks = tasks_result.scalars().all()

    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "workflow_version": run.workflow_version,
        "status": run.status.value,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
        "tasks": [
            {
                "id": t.id,
                "task_key": t.task_key,
                "task_type": t.task_type,
                "status": t.status.value,
                "current_attempt": t.current_attempt,
                "max_attempts": t.max_attempts,
                "depends_on": t.depends_on,
                "input_data": t.input_data,
                "output_data": t.output_data,
                "error_detail": t.error_detail,
            }
            for t in tasks
        ],
    }


@runs_router.get("/{run_id}/replay")
async def get_replay(
    run_id: str, user=Depends(require_viewer), db: AsyncSession = Depends(get_db)
):
    trace = await build_replay_trace(db, run_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Run not found")
    return trace


@runs_router.get("/{run_id}/diff/{other_run_id}")
async def get_diff(
    run_id: str,
    other_run_id: str,
    user=Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await diff_runs(db, run_id, other_run_id)


@runs_router.post("/{run_id}/tasks/{task_key}/retry")
async def force_retry(
    run_id: str,
    task_key: str,
    user=Depends(require_operator),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Task).where(Task.run_id == run_id, Task.task_key == task_key)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"No task '{task_key}' in run '{run_id}'")

    task.status = TaskStatus.PENDING
    task.current_attempt += 1
    task.run_at = datetime.now(timezone.utc)
    task.error_detail = None

    await append_audit(db, "task", task.id, "force_retry", actor=user["sub"],
                       from_status=task.status.value, to_status="pending")
    await db.commit()
    return {"task_key": task_key, "attempt": task.current_attempt}


@runs_router.post("/{run_id}/tasks/{task_key}/skip")
async def skip_task(
    run_id: str,
    task_key: str,
    user=Depends(require_operator),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Task).where(Task.run_id == run_id, Task.task_key == task_key)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"No task '{task_key}' in run '{run_id}'")

    old_status = task.status.value
    task.status = TaskStatus.SKIPPED
    await append_audit(db, "task", task.id, "skipped", actor=user["sub"],
                       from_status=old_status, to_status="skipped")
    await db.commit()
    return {"task_key": task_key, "status": "skipped"}


@runs_router.post("/{run_id}/pause")
async def pause_run(
    run_id: str, user=Depends(require_operator), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = RunStatus.PAUSED
    await append_audit(db, "run", run_id, "paused", actor=user["sub"])
    await db.commit()
    await notify_run_event(run_id, "run.paused")
    return {"run_id": run_id, "status": "paused"}


@runs_router.post("/{run_id}/resume")
async def resume_run(
    run_id: str, user=Depends(require_operator), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = RunStatus.RUNNING
    await append_audit(db, "run", run_id, "resumed", actor=user["sub"])
    await db.commit()
    await notify_run_event(run_id, "run.resumed")
    return {"run_id": run_id, "status": "running"}


# ---------------------------------------------------------------------------
# Chaos / Rehearsal mode
# ---------------------------------------------------------------------------

chaos_router = APIRouter(prefix="/runs", tags=["chaos"])


@chaos_router.post("/{run_id}/rehearsal/kill-worker")
async def kill_worker(
    run_id: str,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not settings.rehearsal_mode_enabled:
        raise HTTPException(
            status_code=403,
            detail="Rehearsal mode is disabled. Set REHEARSAL_MODE_ENABLED=true to enable.",
        )

    # Find the active task and expire its lease immediately
    result = await db.execute(
        select(Task).where(
            Task.run_id == run_id,
            Task.status.in_([TaskStatus.CLAIMED, TaskStatus.RUNNING]),
        )
    )
    tasks = result.scalars().all()
    if not tasks:
        raise HTTPException(status_code=404, detail="No active tasks in this run")

    from datetime import timedelta
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    for t in tasks:
        t.lease_expires_at = past  # will be reclaimed by reaper immediately

    await db.commit()
    return {"killed_tasks": [t.task_key for t in tasks], "message": "Leases expired — reaper will requeue"}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("/verify")
async def verify_audit(user=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    valid, detail = await verify_chain(db)
    return {"valid": valid, "detail": detail}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/v1/runs/{run_id}/stream")
async def run_stream(run_id: str, ws: WebSocket):
    await ws.accept()
    await subscribe(run_id, ws)
    try:
        while True:
            # Keep connection alive; real events are pushed by notify_state_change()
            await asyncio.sleep(30)
            await ws.send_text('{"event":"ping"}')
    except WebSocketDisconnect:
        pass
    finally:
        await unsubscribe(run_id, ws)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

@app.get("/v1/heatmap")
async def heatmap(user=Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Return p50/p95/p99 duration per task type."""
    result = await db.execute(
        select(
            Task.task_type,
            func.count(TaskAttempt.id).label("count"),
            func.percentile_cont(0.5).within_group(TaskAttempt.duration_ms).label("p50"),
            func.percentile_cont(0.95).within_group(TaskAttempt.duration_ms).label("p95"),
            func.percentile_cont(0.99).within_group(TaskAttempt.duration_ms).label("p99"),
        )
        .join(Task, TaskAttempt.task_id == Task.id)
        .group_by(Task.task_type)
    )
    rows = result.all()
    return [
        {
            "task_type": r.task_type,
            "count": r.count,
            "p50_ms": r.p50,
            "p95_ms": r.p95,
            "p99_ms": r.p99,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Mount routers
# ---------------------------------------------------------------------------

app.include_router(auth_router, prefix="/v1")
app.include_router(wf_router, prefix="/v1")
app.include_router(runs_router, prefix="/v1")
app.include_router(chaos_router, prefix="/v1")
app.include_router(audit_router, prefix="/v1")


@app.get("/v1/cron/tick")
@app.post("/v1/cron/tick")
async def cron_tick():
    """
    Vercel Cron endpoint: reaps expired leases, processes pending tasks,
    and updates completed runs. Enables 100% serverless execution on Vercel.
    """
    from orchestra.scheduler import run_completion_checker
    # 1. Process tasks
    processed = await process_tasks_pass()

    # 2. Reap expired leases
    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Task).where(
                Task.status.in_([TaskStatus.CLAIMED, TaskStatus.RUNNING]),
                Task.lease_expires_at < now,
            )
        )
        expired = result.scalars().all()
        for task in expired:
            task.status = TaskStatus.PENDING
            task.lease_id = None
            task.lease_expires_at = None
            task.worker_id = None
            task.current_attempt += 1
        if expired:
            await db.commit()

    return {
        "status": "ok",
        "tasks_processed": processed,
        "leases_reaped": len(expired),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "orchestra"}

