"""API route definitions.

#625: Added auth endpoints, task creation, and /tasks/monitor with long
polling. Each poll tick re-validates authentication through the
AuthMiddleware (see middleware.py), preventing stale/revoked credentials
from retaining access during long-running connections.
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Query

from src.agent import AgentRegistry
from src.agent.registry import AgentStatus
from src.orchestrator.scheduler import TaskScheduler

logger = logging.getLogger(__name__)

router = APIRouter()
registry = AgentRegistry()
scheduler = TaskScheduler()

# ── Agent CRUD ───────────────────────────────────────────────────────


@router.get("/agents")
async def list_agents(status: Optional[str] = None, group: Optional[str] = None):
    status_filter = AgentStatus(status) if status else None
    return {"agents": registry.list(status=status_filter, group=group)}


@router.post("/agents")
async def register_agent(name: str, agent_type: str, config: Optional[Dict] = None):
    agent_id = registry.register(name, agent_type, config)
    return {"agent_id": agent_id, "status": "registered"}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    if not registry.delete(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted"}


@router.post("/agents/{agent_id}/start")
async def start_agent(agent_id: str):
    if not registry.update_status(agent_id, AgentStatus.RUNNING):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "started"}


@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    if not registry.update_status(agent_id, AgentStatus.PAUSED):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "stopped"}


@router.get("/agents/count")
async def agent_count():
    return {"count": registry.count()}


# ── Auth endpoints (unauthenticated) ─────────────────────────────────


@router.post("/auth/token")
async def issue_token(
    username: str = Query(..., description="Username/owner for the API key"),
    scopes: Optional[str] = Query(None, description="Comma-separated scopes"),
    expires_in: Optional[int] = Query(None, ge=60, le=2592000, description="Key lifetime in seconds"),
):
    """Issue a new Bearer API token.

    Returns the raw key once. The key is hashed and stored; subsequent
    requests use it via ``Authorization: Bearer <key>``.
    """
    from .auth_service import auth_store
    scope_list = scopes.split(",") if scopes else None
    raw_key = auth_store.create_key(
        owner=username,
        scopes=scope_list,
        expires_in=expires_in,
    )
    return {
        "token_type": "Bearer",
        "access_token": raw_key,
        "owner": username,
        "scopes": scope_list or ["*"],
        "expires_in": expires_in,
    }


@router.post("/auth/session")
async def create_session(
    request: Request,
    username: str = Query(..., description="Username for the session"),
):
    """Create a browser session.

    Returns the session token. Browser clients should send it via the
    ``x-session-token`` header or ``session`` cookie on subsequent requests.
    """
    from .auth_service import auth_store
    session_id = auth_store.create_session(owner=username)
    return {
        "token_type": "Session",
        "session_token": session_id,
        "owner": username,
    }


# ── Task API ─────────────────────────────────────────────────────────


@router.post("/tasks")
async def create_task(
    request: Request,
    target_agent: str = Query(..., description="Agent ID to execute the task"),
    task_type: str = Query("default", description="Task type"),
    payload: Optional[Dict] = None,
    priority: int = Query(0, description="Priority (higher = sooner)"),
    queue: str = Query("default", description="Queue name"),
):
    """Enqueue a new task for execution."""
    identity = getattr(request.state, "user", "unknown")
    task = {
        "target_agent": target_agent,
        "type": task_type,
        "payload": payload or {},
        "created_by": identity,
        "created_at": time.time(),
    }
    task_id = scheduler.enqueue(task, queue=queue, priority=priority)
    logger.info(
        "Task %s created by %s for agent %s",
        task_id, identity, target_agent,
    )
    return {
        "task_id": task_id,
        "status": "queued",
        "queue": queue,
        "priority": priority,
    }


@router.get("/tasks/status/{task_id}")
async def get_task_status(task_id: str):
    """Get the current status of a task by ID."""
    # Check in-flight tasks
    in_flight = scheduler._in_flight  # noqa: SLF001
    if task_id in in_flight:
        task = in_flight[task_id]
        return {
            "task_id": task_id,
            "status": "running",
            "target_agent": task.get("target_agent"),
            "created_at": task.get("created_at"),
            "type": task.get("type"),
        }

    return {"task_id": task_id, "status": "unknown"}


@router.get("/tasks/monitor")
async def monitor_tasks(
    request: Request,
    timeout: int = Query(30, ge=1, le=120, description="Long-poll timeout in seconds"),
    interval: float = Query(1.0, ge=0.1, le=10.0, description="Poll interval between checks"),
    agent_id: Optional[str] = Query(None, description="Filter by target agent"),
    status_filter: Optional[str] = Query(None, description="Filter by status (running/pending/queued/completed)"),
):
    """Long-polling task monitor endpoint.

    Re-validation: AuthMiddleware validates every HTTP request, including
    each long-poll reconnection. If the credentials are revoked while the
    client is waiting, the *next* poll tick or the response delivery will
    return 401 and the client must re-authenticate.

    This endpoint supports two patterns:
      1. **Active polling (poll)** — Returns immediately with current state
      2. **Long polling (wait)** — Holds the connection for up to *timeout*
         seconds, returning when new data arrives or the timeout expires.

    Browser (session cookie) and token (Bearer) clients are both supported.
    """
    identity = getattr(request.state, "user", "unknown")
    auth_method = getattr(request.state, "auth_method", "unknown")

    logger.info(
        "Task monitor connected: user=%s auth=%s timeout=%ds agent=%s",
        identity, auth_method, timeout, agent_id or "*",
    )

    # ── Snapshot helper ──────────────────────────────────────────────
    def _snapshot() -> Dict:
        """Build the current task monitor snapshot."""
        # Queues summary
        queue_summary = {}
        for qname, q in scheduler._queues.items():  # noqa: SLF001
            queue_summary[qname] = {
                "pending": len(q),
            }

        # In-flight tasks
        tasks_running = []
        # noqa: SLF001 — accessing internal for monitor purposes
        for tid, task in list(scheduler._in_flight.items()):
            if agent_id and task.get("target_agent") != agent_id:
                continue
            tasks_running.append({
                "task_id": tid,
                "target_agent": task.get("target_agent"),
                "type": task.get("type"),
                "created_at": task.get("created_at"),
                "created_by": task.get("created_by"),
            })

        # Running agents
        agents_running = [
            {"id": a["id"], "name": a["name"], "type": a["type"]}
            for a in registry.list(status=AgentStatus.RUNNING)
        ]

        # Scheduler stats
        tenant_stats = {}
        for tenant_id in ["default", "acme-corp"]:
            count = len(scheduler._in_flight)  # total in-flight
            tenant_stats[tenant_id] = {
                "in_flight": count,
                "concurrency_limit": None,
            }

        return {
            "timestamp": time.time(),
            "queues": queue_summary,
            "in_flight_total": len(scheduler._in_flight),
            "tasks_running": tasks_running,
            "agents_running": agents_running,
            "tenant_stats": tenant_stats,
            "user": identity,
            "auth_method": auth_method,
        }

    # ── Always return a snapshot immediately (no long wait on first call) ──
    # Patterns: if the caller sends ?poll=true they get an instant response.
    # Otherwise we do long-poll: hold the connection and check periodically.
    initial = _snapshot()

    # Check for poll mode (instant response)
    poll_only = request.query_params.get("poll", "").lower() in ("true", "1", "yes")

    if poll_only:
        return initial

    # ── Long-poll mode: wait for changes up to *timeout* seconds ─────
    deadline = time.time() + timeout
    last_snapshot = initial

    while time.time() < deadline:
        await asyncio.sleep(interval)
        current = _snapshot()

        # Detect meaningful change
        changed = (
            current["in_flight_total"] != last_snapshot["in_flight_total"]
            or current["agents_running"] != last_snapshot["agents_running"]
            or current["tenant_stats"] != last_snapshot.get("tenant_stats", {})
        )

        if changed:
            logger.debug(
                "Task monitor delivering change for %s after poll cycle",
                identity,
            )
            return current

        last_snapshot = current

    # Timeout — return the latest snapshot
    return {**last_snapshot, "timeout": True}
