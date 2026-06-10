"""
BrowserMind API sidecar — FastAPI server wrapping KernelSession.

Started by Rust via subprocess when the Tauri app launches.
Prints READY:<port> to stdout once uvicorn is accepting connections.
Binds to 127.0.0.1 only; never exposed to the network.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import signal
import sys
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import uvicorn
import time as _time
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from browsermind_core.console.session import KernelSession, DEFAULT_STORE
from browsermind_core.runtime.environment_registry import _REGISTRY, get_all
from browsermind_core.ontology.recovery_candidate import RecoveryCandidate
from browsermind_core.runtime.recovery_registry import RecoveryStrategy


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_session: Optional[KernelSession] = None
_store_dir: str = DEFAULT_STORE
_sidecar_start_time: float = _time.time()
_ws_clients: List = []           # active WebSocket connections
_mission_run_last_ts: float = 0  # rate-limiting for mission/run (#68)


def _get_or_create_api_key() -> str:
    """Return the persistent API key, generating one on first run."""
    key_path = Path(_store_dir) / ".api_key"
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key, encoding="utf-8")
    try:
        key_path.chmod(0o600)
    except OSError:
        pass  # best-effort on Windows
    return key


def get_session() -> KernelSession:
    if _session is None:
        raise RuntimeError("KernelSession not initialised")
    return _session


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session
    _session = await asyncio.to_thread(KernelSession, _store_dir)
    yield
    _session = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="BrowserMind API Sidecar", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API key authentication middleware
# ---------------------------------------------------------------------------

_API_KEY_BYPASS_PATHS = {"/health", "/ready"}


@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    if request.url.path in _API_KEY_BYPASS_PATHS:
        return await call_next(request)
    expected = _get_or_create_api_key()
    provided = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(provided, expected):
        return Response(
            content='{"detail":"Unauthorized"}',
            status_code=401,
            media_type="application/json",
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _exec_status_to_state(status: str) -> str:
    return {
        "running": "running",
        "paused": "paused",
        "succeeded": "completed",
        "failed": "failed",
        "rollback": "failed",
        "forked": "running",
    }.get(status, status)


def _task_status_to_state(status: str) -> str:
    return {
        "pending": "created",
        "running": "running",
        "completed": "completed",
        "failed": "failed",
    }.get(status, status)


def _memory_mb() -> float:
    try:
        import psutil
        proc = psutil.Process()
        return round(proc.memory_info().rss / (1024 * 1024), 2)
    except Exception:
        pass
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 2)
    except Exception:
        pass
    return 0.0


def _find_file_in_ancestors(filename: str) -> Optional[Path]:
    """Walk from CWD upward looking for a file."""
    here = Path.cwd()
    for candidate in [here, *here.parents]:
        p = candidate / filename
        if p.exists():
            return p
    return None


def _find_dir_in_ancestors(dirname: str) -> Optional[Path]:
    here = Path.cwd()
    for candidate in [here, *here.parents]:
        p = candidate / dirname
        if p.is_dir():
            return p
    return None


# ---------------------------------------------------------------------------
# Principals
# ---------------------------------------------------------------------------

@app.get("/api/principals")
async def list_principals():
    session = get_session()
    try:
        raw_keys = await asyncio.to_thread(session.provider.list_keys, "principal")
        results = []
        for k in raw_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.provider.load, "principal", k)
            if not data:
                continue
            results.append({
                "id": str(data.get("id", k)),
                "name": data.get("name", ""),
                "createdAt": _iso(datetime.fromisoformat(data["created_at"]))
                if data.get("created_at") else None,
            })
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

@app.get("/api/personas")
async def list_personas():
    session = get_session()
    try:
        raw_keys = await asyncio.to_thread(session.provider.list_keys, "persona")
        results = []
        for k in raw_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.provider.load, "persona", k)
            if not data:
                continue
            results.append(_persona_to_ts(data))
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/personas/{persona_id}")
async def get_persona(persona_id: str):
    session = get_session()
    try:
        data = await asyncio.to_thread(session.provider.load, "persona", persona_id)
        if not data:
            raise HTTPException(status_code=404, detail="Persona not found")
        return _persona_to_ts(data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _persona_to_ts(data: Dict[str, Any]) -> Dict[str, Any]:
    name = data.get("name", "")
    return {
        "id": str(data.get("id", "")),
        "principalId": str(data.get("principal_id", "")),
        "name": name,
        "displayName": name,
        "avatarUrl": None,
        "bio": data.get("description") or None,
        "createdAt": _iso(datetime.fromisoformat(data["created_at"]))
        if data.get("created_at") else None,
    }


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------

@app.get("/api/identities")
async def list_identities(persona_id: Optional[str] = None):
    session = get_session()
    try:
        identity_index = await asyncio.to_thread(session._load_index, "identity")
        raw_keys = await asyncio.to_thread(session.provider.list_keys, "identity")
        results = []
        env_key_by_id: Dict[str, str] = {}
        for _name, entry in identity_index.items():
            eid = entry.get("id", "")
            env_key = entry.get("env_key", "") or entry.get("environment_key", "")
            if eid and env_key:
                env_key_by_id[eid] = env_key

        for k in raw_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.provider.load, "identity", k)
            if not data:
                continue
            if persona_id and str(data.get("persona_id", "")) != persona_id:
                continue
            results.append(_identity_to_ts(data, env_key_by_id))
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/identities/{identity_id}")
async def get_identity(identity_id: str):
    session = get_session()
    try:
        data = await asyncio.to_thread(session.provider.load, "identity", identity_id)
        if not data:
            raise HTTPException(status_code=404, detail="Identity not found")
        identity_index = await asyncio.to_thread(session._load_index, "identity")
        env_key_by_id: Dict[str, str] = {}
        for _name, entry in identity_index.items():
            eid = entry.get("id", "")
            env_key = entry.get("env_key", "") or entry.get("environment_key", "")
            if eid and env_key:
                env_key_by_id[eid] = env_key
        return _identity_to_ts(data, env_key_by_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _identity_to_ts(data: Dict[str, Any], env_key_by_id: Dict[str, str]) -> Dict[str, Any]:
    raw_id = str(data.get("id", ""))
    env_id = str(data.get("environment_id", ""))
    env_key = env_key_by_id.get(raw_id) or env_key_by_id.get(env_id) or env_id
    return {
        "id": raw_id,
        "personaId": str(data.get("persona_id", "")),
        "environmentKey": env_key,
        "identifier": data.get("identifier", ""),
        "status": data.get("status", "active"),
        "credentialType": "password",
        "lastUsedAt": None,
        "expiresAt": None,
        "createdAt": _iso(datetime.fromisoformat(data["created_at"]))
        if data.get("created_at") else None,
    }


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

@app.get("/api/environments")
async def list_environments():
    session = get_session()
    try:
        store = Path(session.store_dir)
        registry = await asyncio.to_thread(get_all)
        results = []
        for entry in registry:
            profile_path = store / "profiles" / entry.key
            connected = await asyncio.to_thread(
                lambda p=profile_path: p.is_dir() and any(p.iterdir())
            )
            if entry.benchmark:
                if entry.benchmark.is_gate:
                    compat = "full"
                else:
                    compat = "partial"
                label = entry.benchmark.label
            else:
                compat = "none"
                label = entry.description or entry.key

            results.append({
                "key": entry.key,
                "label": label,
                "family": entry.family,
                "startUrl": entry.start_url,
                "status": "connected" if connected else "needs_login",
                "cookieCount": None,
                "storageStateBytes": None,
                "lastLoginAt": None,
                "replayCompatibility": compat,
                "iconHint": entry.key,
            })
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/environments/{env_key}")
async def get_environment(env_key: str):
    session = get_session()
    try:
        store = Path(session.store_dir)
        registry = await asyncio.to_thread(get_all)
        for entry in registry:
            if entry.key != env_key:
                continue
            profile_path = store / "profiles" / entry.key
            connected = await asyncio.to_thread(
                lambda p=profile_path: p.is_dir() and any(p.iterdir())
            )
            if entry.benchmark:
                compat = "full" if entry.benchmark.is_gate else "partial"
                label = entry.benchmark.label
            else:
                compat = "none"
                label = entry.description or entry.key
            return {
                "key": entry.key,
                "label": label,
                "family": entry.family,
                "startUrl": entry.start_url,
                "status": "connected" if connected else "needs_login",
                "cookieCount": None,
                "storageStateBytes": None,
                "lastLoginAt": None,
                "replayCompatibility": compat,
                "iconHint": entry.key,
            }
        raise HTTPException(status_code=404, detail="Environment not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@app.get("/api/tasks")
async def list_tasks():
    session = get_session()
    try:
        task_index = await asyncio.to_thread(session._load_index, "task")
        # goal lookup by task id
        goal_by_id: Dict[str, str] = {}
        persona_by_id: Dict[str, str] = {}
        for name, entry in task_index.items():
            tid = entry.get("id", "")
            goal_by_id[tid] = name
            if "persona_id" in entry:
                persona_by_id[tid] = entry["persona_id"]

        exec_keys = await asyncio.to_thread(session.repo.provider.list_keys, "executions")
        task_map: Dict[str, Dict[str, Any]] = {}

        for k in exec_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.repo.provider.load, "executions", k)
            if not data:
                continue
            tid = str(data.get("task_id", ""))
            if not tid:
                continue
            exec_state = _exec_status_to_state(data.get("status", "running"))
            updated_at = data.get("updated_at") or data.get("created_at")
            if tid not in task_map:
                ctx = data.get("context") or {}
                task_map[tid] = {
                    "id": tid,
                    "personaId": str(ctx.get("persona_id") or persona_by_id.get(tid, "")),
                    "environmentKey": None,
                    "goal": goal_by_id.get(tid, ""),
                    "state": exec_state,
                    "progress": {"current": 0, "total": 1},
                    "missingResources": [],
                    "nextAction": None,
                    "lastEventAt": _iso(datetime.fromisoformat(updated_at)) if updated_at else None,
                    "createdAt": _iso(datetime.fromisoformat(data["created_at"]))
                    if data.get("created_at") else None,
                    "updatedAt": _iso(datetime.fromisoformat(updated_at)) if updated_at else None,
                }
            else:
                # Update state to latest execution
                task_map[tid]["state"] = exec_state
                if updated_at:
                    task_map[tid]["lastEventAt"] = _iso(datetime.fromisoformat(updated_at))

        # Add tasks from index that have no executions yet
        for name, entry in task_index.items():
            tid = entry.get("id", "")
            if tid and tid not in task_map:
                task_map[tid] = {
                    "id": tid,
                    "personaId": entry.get("persona_id", ""),
                    "environmentKey": None,
                    "goal": name,
                    "state": "created",
                    "progress": {"current": 0, "total": 1},
                    "missingResources": [],
                    "nextAction": None,
                    "lastEventAt": None,
                    "createdAt": None,
                    "updatedAt": None,
                }

        return list(task_map.values())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    session = get_session()
    try:
        task_index = await asyncio.to_thread(session._load_index, "task")
        goal_by_id: Dict[str, str] = {}
        persona_by_id: Dict[str, str] = {}
        for name, entry in task_index.items():
            tid = entry.get("id", "")
            goal_by_id[tid] = name
            if "persona_id" in entry:
                persona_by_id[tid] = entry["persona_id"]

        exec_keys = await asyncio.to_thread(session.repo.provider.list_keys, "executions")
        task_state = "created"
        last_updated = None
        persona_id = persona_by_id.get(task_id, "")
        for k in exec_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.repo.provider.load, "executions", k)
            if not data or str(data.get("task_id", "")) != task_id:
                continue
            task_state = _exec_status_to_state(data.get("status", "running"))
            last_updated = data.get("updated_at") or data.get("created_at")
            ctx = data.get("context") or {}
            persona_id = persona_id or str(ctx.get("persona_id", ""))

        goal = goal_by_id.get(task_id, "")
        if not goal and task_id not in goal_by_id.values():
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "id": task_id,
            "personaId": persona_id,
            "environmentKey": None,
            "goal": goal,
            "state": task_state,
            "progress": {"current": 0, "total": 1},
            "missingResources": [],
            "nextAction": None,
            "lastEventAt": _iso(datetime.fromisoformat(last_updated)) if last_updated else None,
            "createdAt": None,
            "updatedAt": _iso(datetime.fromisoformat(last_updated)) if last_updated else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/executions")
async def list_executions(taskId: Optional[str] = None, state: Optional[str] = None):
    session = get_session()
    try:
        exec_keys = await asyncio.to_thread(session.repo.provider.list_keys, "executions")
        results = []
        for k in exec_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.repo.provider.load, "executions", k)
            if not data:
                continue
            if taskId and str(data.get("task_id", "")) != taskId:
                continue
            row = _execution_to_ts(data)
            if state and row.get("state") != state:
                continue
            results.append(row)
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/executions/{execution_id}")
async def get_execution(execution_id: str):
    session = get_session()
    try:
        data = await asyncio.to_thread(session.repo.provider.load, "executions", execution_id)
        if not data:
            raise HTTPException(status_code=404, detail="Execution not found")
        return _execution_to_ts(data, repo=session.repo, outcome_repo=session.outcome_repo)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class ExecutionActionBody(BaseModel):
    action: str  # "pause" | "resume" | "retry" | "cancel"


@app.post("/api/executions/{execution_id}/act")
async def execution_act(execution_id: str, body: ExecutionActionBody):
    session = get_session()
    try:
        exec_obj = await asyncio.to_thread(session.repo.load_execution, UUID(execution_id))
        if not exec_obj:
            raise HTTPException(status_code=404, detail="Execution not found")

        action = body.action
        if action == "pause":
            exec_obj.status = "paused"
        elif action == "resume":
            exec_obj.status = "running"
        elif action == "retry":
            exec_obj.status = "running"
            exec_obj.retry_count = (exec_obj.retry_count or 0) + 1
        elif action == "cancel":
            exec_obj.status = "failed"
            exec_obj.failure_reason = "Cancelled by operator"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        await asyncio.to_thread(session.repo.save_execution, exec_obj)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _execution_to_ts(data: Dict[str, Any], repo=None, outcome_repo=None) -> Dict[str, Any]:
    from uuid import UUID as _UUID
    import hashlib as _hashlib
    status = data.get("status", "running")
    exec_id = data.get("id")
    exec_id_str = str(exec_id or "")

    snapshots = []
    if repo and exec_id:
        try:
            snaps = repo.load_all_snapshots(_UUID(exec_id_str))
            for i, s in enumerate(snaps):
                ts = _iso(s.created_at) if hasattr(s, "created_at") and s.created_at else None
                snapshots.append({
                    "id": f"snap-{exec_id_str[:8]}-{i}",
                    "sequence": s.sequence,
                    "kind": "pre_step",
                    "timestamp": ts or _iso(datetime.now(timezone.utc)),
                    "evidenceUri": getattr(s, "evidence_uri", None),
                })
        except Exception:
            pass

    events: List[Dict[str, Any]] = []
    if outcome_repo and exec_id:
        try:
            records = outcome_repo.load_all()
            step_seq = 0
            for r in records:
                if str(r.scope_id) != exec_id_str:
                    continue
                metrics = r.metrics or {}
                action = metrics.get("action", "unknown")
                role = metrics.get("role", "")
                name = metrics.get("name", "")
                step_seq += 1
                kind = action if action in (
                    "navigate", "click", "fill", "extract", "verify", "pause", "resume", "fail", "snapshot"
                ) else "click"
                resolver = metrics.get("resolution_strategy")
                detail_parts = []
                if not r.success and metrics.get("failure_class"):
                    detail_parts.append(metrics["failure_class"])
                if resolver:
                    detail_parts.append(f"via {resolver}")
                events.append({
                    "id": str(r.id),
                    "timestamp": _iso(r.timestamp),
                    "kind": kind,
                    "summary": f"{action} {role}:{name}".strip(": "),
                    "detail": " | ".join(detail_parts) if detail_parts else None,
                    "resolverStrategy": resolver,
                })
        except Exception:
            pass

    return {
        "id": exec_id_str,
        "taskId": str(data.get("task_id", "")),
        "workflowId": str(data["workflow_instance_id"]) if data.get("workflow_instance_id") else None,
        "state": _exec_status_to_state(status),
        "startedAt": _iso(datetime.fromisoformat(data["created_at"])) if data.get("created_at") else None,
        "endedAt": _iso(datetime.fromisoformat(data["updated_at"]))
        if status in ("succeeded", "failed", "rollback") and data.get("updated_at") else None,
        "retryCount": data.get("retry_count", 0),
        "currentStepSeq": len(events) if events else None,
        "snapshots": snapshots,
        "checkpoints": [],
        "recoveryHistory": [],
        "events": events,
    }


# ---------------------------------------------------------------------------
# Workflow Templates
# ---------------------------------------------------------------------------

@app.get("/api/workflows")
async def list_workflows():
    session = get_session()
    try:
        templates = await asyncio.to_thread(session.workflow_store.list_templates)
        results = []
        for entry in templates:
            tid = entry.get("id")
            if not tid:
                continue
            tpl = await asyncio.to_thread(session.workflow_store.get_template, UUID(tid))
            if not tpl:
                continue
            family_key = entry.get("family_key") or tpl.metadata.get("family_key", "")
            results.append({
                "id": str(tpl.id),
                "name": tpl.name,
                "description": tpl.description,
                "version": 1,
                "environmentKey": family_key or None,
                "steps": tpl.steps,
                "createdAt": _iso(tpl.created_at),
                "updatedAt": _iso(tpl.updated_at),
            })
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Replay Reports
# ---------------------------------------------------------------------------

@app.get("/api/replays")
async def list_replay_reports():
    try:
        reports_dir = _find_dir_in_ancestors(os.path.join("reports", "benchmark"))
        if not reports_dir:
            return []
        results = []
        files = await asyncio.to_thread(
            lambda: [f for f in reports_dir.iterdir() if f.suffix == ".json"]
        )
        for fpath in files:
            raw = await asyncio.to_thread(fpath.read_text, encoding="utf-8")
            try:
                doc = json.loads(raw)
            except Exception:
                continue
            workflows = doc.get("workflows", {})
            for wf_name, wf_data in workflows.items():
                runs = wf_data.get("raw", [])
                for idx, run in enumerate(runs):
                    uid_src = f"{fpath.name}:{wf_name}:{idx}"
                    rid = hashlib.md5(uid_src.encode()).hexdigest()
                    results.append({
                        "id": rid,
                        "executionId": None,
                        "workflowId": wf_name,
                        "environmentKey": wf_name,
                        "status": "OK" if run.get("success") else "FAIL",
                        "resolutionRate": float(run.get("resolution_rate", 0.0)),
                        "falsePositiveRate": None,
                        "taskCompletionRate": float(run.get("completion_rate", 0.0)),
                        "criticalPath": [],
                        "failureCategory": run.get("status") if not run.get("success") else None,
                        "failureReason": None,
                        "totalSteps": int(run.get("steps", 0)),
                        "resolvedSteps": int(run.get("resolved", 0)),
                        "attemptedSteps": int(run.get("steps", 0)),
                        "stepOutcomes": [],
                        "createdAt": _iso(datetime.fromtimestamp(
                            fpath.stat().st_mtime, tz=timezone.utc
                        )),
                    })
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Ledger Events
# ---------------------------------------------------------------------------

@app.get("/api/ledger")
async def list_ledger_events():
    session = get_session()
    try:
        records = await asyncio.to_thread(session.outcome_repo.tail, 200)
        results = []
        for r in records:
            metrics = r.metrics or {}
            action = metrics.get("action", "?")
            role = metrics.get("role", "?")
            name = metrics.get("name", "?")
            results.append({
                "id": str(r.id),
                "timestamp": _iso(r.timestamp),
                "kind": "execution",
                "entityType": metrics.get("action") or r.scope,
                "entityId": str(r.scope_id),
                "personaId": str(r.persona_id),
                "environmentKey": r.environment_instance or None,
                "before": None,
                "after": None,
                "summary": f"{action} {role}:{name}",
            })
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@app.get("/api/memory")
async def list_memory():
    session = get_session()
    try:
        results = []

        proc_keys = await asyncio.to_thread(session.provider.list_keys, "procedural_memory")
        for k in proc_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.provider.load, "procedural_memory", k)
            if not data:
                continue
            knowledge = data.get("knowledge", "")
            results.append({
                "id": str(data.get("id", k)),
                "type": "procedural",
                "title": knowledge[:50],
                "content": knowledge,
                "relatedEntities": [],
                "tags": [data.get("memory_type", "procedural")],
                "createdAt": _iso(datetime.fromisoformat(data["created_at"]))
                if data.get("created_at") else None,
            })

        lessons_path = _find_file_in_ancestors("lessons.jsonl")
        if lessons_path:
            raw_lines = await asyncio.to_thread(lessons_path.read_text, encoding="utf-8")
            for i, line in enumerate(raw_lines.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                content = rec.get("lesson") or rec.get("content") or str(rec)
                results.append({
                    "id": f"lesson-{i}",
                    "type": "episodic",
                    "title": content[:50],
                    "content": content,
                    "relatedEntities": [],
                    "tags": ["episodic"],
                    "createdAt": rec.get("timestamp") or None,
                })

        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics/metrics")
async def get_analytics():
    session = get_session()
    try:
        records = await asyncio.to_thread(session.outcome_repo.load_all)

        step_records = [r for r in records if r.scope == "step"]
        exec_records = [r for r in records if r.scope == "execution"]
        task_records = [r for r in records if r.scope == "task"]

        # replayResolutionRate
        if step_records:
            resolution_rate = sum(1 for r in step_records if r.success) / len(step_records)
        elif exec_records:
            rates = [r.metrics.get("resolution_rate", 0.0) for r in exec_records if "resolution_rate" in r.metrics]
            resolution_rate = sum(rates) / len(rates) if rates else 0.0
        else:
            resolution_rate = 0.0

        # taskCompletionRate
        if exec_records:
            task_completion = sum(1 for r in exec_records if r.success) / len(exec_records)
        elif task_records:
            task_completion = sum(1 for r in task_records if r.success) / len(task_records)
        else:
            task_completion = 0.0

        # identityDrift
        identity_index = await asyncio.to_thread(session._load_index, "identity")
        id_keys = await asyncio.to_thread(session.provider.list_keys, "identity")
        total_ids = len([k for k in id_keys if not k.startswith("_")])
        inactive_ids = 0
        for k in id_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.provider.load, "identity", k)
            if data and data.get("status", "active") != "active":
                inactive_ids += 1
        identity_drift = inactive_ids / total_ids if total_ids else 0.0

        # failureOntology
        failure_counts: Dict[str, int] = defaultdict(int)
        for r in step_records:
            if not r.success:
                fc = r.metrics.get("failure_class", "unknown")
                failure_counts[fc] += 1
        total_failures = sum(failure_counts.values()) or 1
        sorted_failures = sorted(failure_counts.items(), key=lambda x: -x[1])[:8]
        failure_ontology = [
            {"category": k, "share": round(v / total_failures, 4)}
            for k, v in sorted_failures
        ]

        # trend: last 14 days daily resolution rate
        from collections import defaultdict as dd
        day_success: Dict[str, int] = dd(int)
        day_total: Dict[str, int] = dd(int)
        for r in step_records:
            day = r.timestamp.strftime("%Y-%m-%d")
            day_total[day] += 1
            if r.success:
                day_success[day] += 1

        all_days = sorted(day_total.keys())[-14:]
        trend = [
            {
                "date": d,
                "resolutionRate": round(day_success[d] / day_total[d], 4) if day_total[d] else 0.0,
                "fpr": 0.0,
            }
            for d in all_days
        ]

        return {
            "replayResolutionRate": round(resolution_rate, 4),
            "falsePositiveRate": 0.0,
            "taskCompletionRate": round(task_completion, 4),
            "identityDrift": round(identity_drift, 4),
            "replayCeiling": 1.0,
            "environmentStability": 1.0,
            "failureOntology": failure_ontology,
            "trend": trend,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# System Status
# ---------------------------------------------------------------------------

@app.get("/api/system/status")
async def system_status():
    session = get_session()
    try:
        exec_keys = await asyncio.to_thread(session.repo.provider.list_keys, "executions")
        active = 0
        for k in exec_keys:
            if k.startswith("_"):
                continue
            data = await asyncio.to_thread(session.repo.provider.load, "executions", k)
            if data and data.get("status") == "running":
                active += 1

        return {
            "activeSessions": active,
            "backgroundJobs": 0,
            "memoryMb": await asyncio.to_thread(_memory_mb),
            "replayStatus": "idle",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

@app.get("/api/training/status")
async def training_status():
    try:
        dataset_path = _find_file_in_ancestors(os.path.join("training", "dataset_v1.jsonl"))
        episode_count = 0
        if dataset_path:
            raw = await asyncio.to_thread(dataset_path.read_text, encoding="utf-8")
            episode_count = sum(1 for line in raw.splitlines() if line.strip())

        ckpt_path = _find_file_in_ancestors("bc_v2_checkpoint.pt")
        checkpoint_loaded = ckpt_path is not None
        action_acc: Optional[float] = None
        val_loss: Optional[float] = None
        last_trained_at: Optional[str] = None

        if ckpt_path:
            last_trained_at = _iso(datetime.fromtimestamp(
                ckpt_path.stat().st_mtime, tz=timezone.utc
            ))
            try:
                import torch
                ckpt = await asyncio.to_thread(
                    torch.load, str(ckpt_path), map_location="cpu"
                )
                meta = ckpt.get("meta", ckpt.get("metadata", {}))
                action_acc = meta.get("action_acc")
                val_loss = meta.get("val_loss")
            except Exception:
                pass

        return {
            "episodeCount": episode_count,
            "checkpointLoaded": checkpoint_loaded,
            "checkpointPath": str(ckpt_path) if ckpt_path else None,
            "actionAcc": action_acc,
            "valLoss": val_loss,
            "lastTrainedAt": last_trained_at,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/training/train")
async def training_train():
    try:
        train_script = _find_file_in_ancestors("train_bc_v2.py")
        cmd = [sys.executable, str(train_script)] if train_script else [sys.executable, "train_bc_v2.py"]
        await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return {"started": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/training/self-train")
async def training_self_train():
    try:
        bm_script = _find_file_in_ancestors("bm.py")
        cmd = [sys.executable, str(bm_script), "self-train"] if bm_script else [sys.executable, "bm.py", "self-train"]
        await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return {"started": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Recovery Candidates
# ---------------------------------------------------------------------------

@app.get("/api/recovery/candidates")
async def list_recovery_candidates():
    session = get_session()
    try:
        candidates = await asyncio.to_thread(session.recovery_candidate_registry.list)
        return [
            {
                "id": str(c.id),
                "name": c.name,
                "primitive": c.primitive,
                "depth": None,
                "support": c.support,
                "lift": c.lift,
                "status": c.status,
                "createdAt": _iso(c.created_at),
            }
            for c in candidates
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/recovery/candidates/{candidate_id}/approve")
async def approve_recovery_candidate(candidate_id: str):
    session = get_session()
    try:
        candidate = await asyncio.to_thread(
            session.recovery_candidate_registry.get, UUID(candidate_id)
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        await asyncio.to_thread(
            session.recovery_candidate_registry.update_status,
            UUID(candidate_id),
            "approved",
        )

        strategy = RecoveryStrategy(
            name=candidate.name,
            predicate=candidate.predicate,
            primitive=candidate.primitive,
            depth=1,
            source="mined",
            candidate_id=str(candidate.id),
        )
        await asyncio.to_thread(session.recovery_registry.append, strategy)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/recovery/candidates/{candidate_id}/reject")
async def reject_recovery_candidate(candidate_id: str):
    session = get_session()
    try:
        await asyncio.to_thread(
            session.recovery_candidate_registry.update_status,
            UUID(candidate_id),
            "rejected",
        )
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

@app.get("/api/benchmark/reports")
async def list_benchmark_reports():
    try:
        reports_dir = _find_dir_in_ancestors(os.path.join("reports", "benchmark"))
        if not reports_dir:
            return []
        results = []
        files = await asyncio.to_thread(
            lambda: sorted(
                [f for f in reports_dir.iterdir() if f.suffix == ".json"],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
        )
        for fpath in files:
            raw = await asyncio.to_thread(fpath.read_text, encoding="utf-8")
            try:
                doc = json.loads(raw)
            except Exception:
                continue
            workflows = doc.get("workflows", {})
            wf_count = len(workflows)
            all_runs: List[Dict[str, Any]] = []
            wf_summaries = []
            for wf_name, wf_data in workflows.items():
                runs = wf_data.get("raw", [])
                all_runs.extend(runs)
                success_runs = [r for r in runs if r.get("success")]
                rate = len(success_runs) / len(runs) if runs else 0.0
                wf_summaries.append({
                    "name": wf_name,
                    "successRate": round(rate, 4),
                    "description": wf_data.get("description", ""),
                })

            agg = sum(1 for r in all_runs if r.get("success")) / len(all_runs) if all_runs else 0.0
            runs_per_wf = len(all_runs) // wf_count if wf_count else 0

            stat = await asyncio.to_thread(fpath.stat)
            results.append({
                "filename": fpath.name,
                "timestamp": _iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)),
                "aggregateSuccessRate": round(agg, 4),
                "workflowCount": wf_count,
                "runsPerWorkflow": runs_per_wf,
                "workflows": wf_summaries,
            })
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/benchmark/run")
async def run_benchmark():
    try:
        bm_script = _find_file_in_ancestors("run_benchmark.py")
        cmd = (
            [sys.executable, str(bm_script), "--headless"]
            if bm_script
            else [sys.executable, "run_benchmark.py", "--headless"]
        )
        await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return {"started": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

class ReplayStartBody(BaseModel):
    templateName: str
    envKey: str
    personaName: str
    headless: bool = False


@app.post("/api/replay/start")
async def replay_start(body: ReplayStartBody):
    try:
        bm_script = _find_file_in_ancestors("bm.py")
        cmd = [
            sys.executable,
            str(bm_script) if bm_script else "bm.py",
            "replay",
            "start",
            body.templateName,
            "--env", body.envKey,
            "--persona", body.personaName,
        ]
        if body.headless:
            cmd.append("--headless")
        await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return {"started": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Objective Function
# ---------------------------------------------------------------------------

class ObjectiveScoreRequest(BaseModel):
    execution_id: Optional[str] = None
    min_steps: int = 0


@app.post("/api/objective/score")
async def objective_score(body: ObjectiveScoreRequest):
    """Score one or all executions in the ledger.

    If ``execution_id`` is provided, returns the score for that execution only.
    Otherwise, returns scores for all executions (keyed by execution_id).
    """
    try:
        session = get_session()
        from browsermind_core.training.episode_extractor import extract_bc_episodes
        from browsermind_core.training.objective_fn import CorpusStats, score_all_executions, score_execution

        episodes = await asyncio.to_thread(
            extract_bc_episodes,
            session.ledger,
            success_only=False,
            min_steps=body.min_steps,
        )
        if not episodes:
            return {"scores": {}, "corpus_stats": {"total_envs": 0, "total_executions": 0}}

        stats = CorpusStats.from_episodes(episodes)
        all_scores = score_all_executions(episodes, stats)

        if body.execution_id:
            sc = all_scores.get(body.execution_id)
            if sc is None:
                raise HTTPException(status_code=404, detail=f"execution_id {body.execution_id!r} not found in ledger")
            return {"execution_id": body.execution_id, "score": sc.as_dict()}

        return {
            "scores": {eid: sc.as_dict() for eid, sc in all_scores.items()},
            "corpus_stats": {
                "total_envs": stats.total_envs,
                "total_executions": sum(stats.workflow_class_exec_count.values()),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Explore
# ---------------------------------------------------------------------------

class ExploreStartBody(BaseModel):
    siteKey: str
    budget: int = 50
    headless: bool = False
    personaName: str = "validator"


@app.post("/api/explore/start")
async def explore_start(body: ExploreStartBody):
    try:
        bm_script = _find_file_in_ancestors("bm.py")
        cmd = [
            sys.executable,
            str(bm_script) if bm_script else "bm.py",
            "explore",
            "--site", body.siteKey,
            "--budget", str(body.budget),
            "--persona", body.personaName,
        ]
        if body.headless:
            cmd.append("--headless")
        await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"started": True, "runId": f"{body.siteKey}-{body.budget}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/explore/runs")
async def explore_runs():
    """Return all saved ExplorationResult records from ~/.browsermind/explore_runs/."""
    try:
        from pathlib import Path as _Path
        runs_dir = _Path.home() / ".browsermind" / "explore_runs"
        if not runs_dir.exists():
            return []

        def _load():
            results = []
            for fpath in sorted(runs_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
                try:
                    doc = json.loads(fpath.read_text(encoding="utf-8"))
                    results.append({
                        "runId":                  fpath.stem,
                        "siteKey":                doc.get("site_key", ""),
                        "budget":                 doc.get("budget", 0),
                        "status":                 doc.get("status", "complete"),
                        "stepsExecuted":          doc.get("steps_executed", 0),
                        "experiencesDiscovered":  doc.get("experiences_discovered", []),
                        "hypothesisCount":        len(doc.get("hypothesis_hashes", [])),
                        "durationSeconds":        doc.get("duration_seconds", 0.0),
                        "error":                  doc.get("error"),
                        "startedAt":              doc.get("started_at", ""),
                    })
                except Exception:
                    pass
            return results

        return await asyncio.to_thread(_load)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/explore/live")
async def explore_live():
    """Read live exploration state from ~/.browsermind/_live_state.json."""
    try:
        from pathlib import Path as _Path
        live_path = _Path.home() / ".browsermind" / "_live_state.json"
        if not live_path.exists():
            return None
        raw = await asyncio.to_thread(live_path.read_text, encoding="utf-8")
        doc = json.loads(raw)
        site_key = doc.get("environment_instance", doc.get("site_key", ""))
        return {
            "runId":                 "live",
            "siteKey":               site_key,
            "budget":                doc.get("budget", 0),
            "status":                "running" if not doc.get("is_paused") else "running",
            "stepsExecuted":         doc.get("seq", 0),
            "experiencesDiscovered": [],
            "hypothesisCount":       0,
            "durationSeconds":       0.0,
            "error":                 None,
            "startedAt":             doc.get("updated_at", ""),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/explore/ledger-stats")
async def explore_ledger_stats():
    """Return FallbackLedger stats from ~/.browsermind/fallback_ledger.json."""
    try:
        def _load():
            from browsermind_core.representation.fallback_ledger import FallbackLedger
            ledger = FallbackLedger()
            return ledger.stats()

        stats = await asyncio.to_thread(_load)
        return {
            "uniqueFragments":    stats["unique_fragments"],
            "totalObservations":  stats["total_observations"],
            "multiSiteFragments": stats["multi_site_fragments"],
            "topFragments": [
                {"fragment": f["fragment"], "freq": f["freq"], "sites": f["sites"]}
                for f in stats.get("top_fragments", [])
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/explore/vocab-proposals")
async def explore_vocab_proposals():
    """Return VocabProposalStore summary from ~/.browsermind/vocab_proposals.json."""
    try:
        def _load():
            from browsermind_core.representation.vocab_inductor import VocabProposalStore
            store = VocabProposalStore()
            return store.stats()

        stats = await asyncio.to_thread(_load)
        return {
            "total":    stats["total"],
            "byStatus": stats.get("by_status", {}),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Mission Runtime
# ---------------------------------------------------------------------------

_mission_proc: Optional[asyncio.subprocess.Process] = None


def _load_mission_queue_raw(store_dir: str) -> List[dict]:
    path = Path(store_dir) / "missions" / "queue.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("entries", [])
    except Exception:
        return []


class MissionAddBody(BaseModel):
    siteKey: str
    persona: str = "validator"
    budget: int = 200
    tags: List[str] = []
    maxRetries: int = 2


class MissionAddBulkBody(BaseModel):
    siteKeys: List[str]
    persona: str = "validator"
    budget: int = 200
    tags: List[str] = []


class MissionRunBody(BaseModel):
    hours: Optional[float] = None
    maxSites: Optional[int] = None
    headless: bool = False
    persona: str = "validator"


class MissionClearBody(BaseModel):
    status: str


@app.get("/api/missions")
async def missions_list(status: Optional[str] = None):
    def _load():
        entries = _load_mission_queue_raw(_store_dir)
        if status:
            entries = [e for e in entries if e.get("status") == status]
        return entries
    return await asyncio.to_thread(_load)


@app.get("/api/missions/counts")
async def missions_counts():
    def _load():
        entries = _load_mission_queue_raw(_store_dir)
        counts: Dict[str, int] = {
            "pending": 0, "running": 0, "done": 0,
            "failed": 0, "paused": 0, "skipped": 0,
        }
        for e in entries:
            s = e.get("status", "pending")
            counts[s] = counts.get(s, 0) + 1
        return counts
    return await asyncio.to_thread(_load)


@app.get("/api/missions/live")
async def missions_live():
    """Combined live state: _live_state.json + queue counts + running entry."""
    def _load():
        live_path = Path(_store_dir) / "_live_state.json"
        live: Dict[str, Any] = {}
        if live_path.exists():
            try:
                live = json.loads(live_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        entries = _load_mission_queue_raw(_store_dir)
        counts: Dict[str, int] = {
            "pending": 0, "running": 0, "done": 0,
            "failed": 0, "paused": 0, "skipped": 0,
        }
        for e in entries:
            s = e.get("status", "pending")
            counts[s] = counts.get(s, 0) + 1

        running_entry = next((e for e in entries if e.get("status") == "running"), None)
        paused_entries = [e for e in entries if e.get("status") == "paused"]

        current_site = (
            live.get("environment_instance")
            or (running_entry.get("site_key") if running_entry else None)
        )
        is_worker_running = bool(running_entry or live.get("environment_instance"))

        return {
            "isWorkerRunning":  is_worker_running,
            "currentSite":      current_site,
            "currentAction":    live.get("current_action"),
            "currentRole":      live.get("current_target_role"),
            "currentName":      live.get("current_target_name"),
            "stepSeq":          live.get("current_step_seq", 0),
            "stepsSoFar":       live.get("step_count_so_far", 0),
            "successSoFar":     live.get("successful_so_far", 0),
            "failedSoFar":      live.get("failed_so_far", 0),
            "totalSteps":       live.get("total_steps", 0),
            "isPaused":         bool(live.get("is_paused", False)),
            "lastUpdateTs":     live.get("last_update_ts"),
            "queueCounts":      counts,
            "needsHuman":       len(paused_entries) > 0,
            "pausedSites":      [e.get("site_key", "") for e in paused_entries],
            "currentPersona":   running_entry.get("persona") if running_entry else None,
            "currentBudget":    running_entry.get("budget") if running_entry else None,
        }

    return await asyncio.to_thread(_load)


@app.get("/api/missions/worker-status")
async def missions_worker_status():
    global _mission_proc
    if _mission_proc is None:
        return {"running": False, "pid": None}
    if _mission_proc.returncode is None:
        return {"running": True, "pid": _mission_proc.pid}
    _mission_proc = None
    return {"running": False, "pid": None}


@app.post("/api/missions/add")
async def missions_add(body: MissionAddBody):
    def _add():
        from browsermind_core.mission.mission_queue import MissionQueue
        q = MissionQueue(Path(_store_dir))
        e = q.add(
            body.siteKey,
            persona=body.persona,
            budget=body.budget,
            tags=body.tags,
            max_retries=body.maxRetries,
        )
        return {"id": e.id, "siteKey": e.site_key, "status": e.status, "added": True}
    return await asyncio.to_thread(_add)


@app.post("/api/missions/add-bulk")
async def missions_add_bulk(body: MissionAddBulkBody):
    def _add():
        from browsermind_core.mission.mission_queue import MissionQueue
        q = MissionQueue(Path(_store_dir))
        added = q.add_bulk(
            body.siteKeys,
            persona=body.persona,
            budget=body.budget,
            tags=body.tags,
        )
        return {"added": added, "total": len(body.siteKeys)}
    return await asyncio.to_thread(_add)


@app.post("/api/missions/run")
async def missions_run(body: MissionRunBody):
    global _mission_proc
    try:
        bm_script = _find_file_in_ancestors("bm.py")
        cmd = [
            sys.executable,
            str(bm_script) if bm_script else "bm.py",
            "mission", "run",
            "--persona", body.persona,
        ]
        if body.hours is not None:
            cmd += ["--hours", str(body.hours)]
        if body.maxSites is not None:
            cmd += ["--max-sites", str(body.maxSites)]
        if body.headless:
            cmd.append("--headless")

        _mission_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"started": True, "pid": _mission_proc.pid}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/missions/stop")
async def missions_stop():
    global _mission_proc
    if _mission_proc is None:
        return {"stopped": False, "reason": "no_worker"}
    try:
        _mission_proc.terminate()
        _mission_proc = None
        # Also clear any stale 'running' entry in the queue
        def _cleanup():
            from browsermind_core.mission.mission_queue import MissionQueue
            q = MissionQueue(Path(_store_dir))
            q.reset_running()
        await asyncio.to_thread(_cleanup)
        return {"stopped": True}
    except Exception as exc:
        return {"stopped": False, "reason": str(exc)}


@app.post("/api/missions/{site_key}/resume")
async def missions_resume(site_key: str):
    def _resume():
        from browsermind_core.mission.mission_queue import MissionQueue
        q = MissionQueue(Path(_store_dir))
        ok = q.resume(site_key)
        return {"resumed": ok}
    return await asyncio.to_thread(_resume)


@app.post("/api/missions/clear")
async def missions_clear(body: MissionClearBody):
    def _clear():
        from browsermind_core.mission.mission_queue import MissionQueue
        q = MissionQueue(Path(_store_dir))
        removed = q.clear(body.status)
        return {"removed": removed}
    return await asyncio.to_thread(_clear)


# ---------------------------------------------------------------------------
# Health endpoint (#69)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Liveness check — returns sidecar version, uptime, and queue counts."""
    def _info():
        uptime = round(_time.time() - _sidecar_start_time, 1)
        counts: Dict[str, int] = {}
        try:
            from browsermind_core.mission.mission_queue import MissionQueue
            counts = MissionQueue(Path(_store_dir)).counts()
        except Exception:
            pass
        return {
            "status":     "ok",
            "uptime_s":   uptime,
            "version":    "browsermind-sidecar/1.0",
            "store_dir":  _store_dir,
            "queue":      counts,
            "ws_clients": len(_ws_clients),
        }
    return await asyncio.to_thread(_info)


# ---------------------------------------------------------------------------
# Screenshot endpoint (#52) — latest browser screenshot as base64 PNG
# ---------------------------------------------------------------------------

@app.get("/api/screenshot/current")
async def screenshot_current():
    """
    Return the most recent browser screenshot as a base64 PNG.
    Falls back to the live_state current_site URL thumbnail if no active browser.
    """
    live_path = Path(_store_dir) / "_live_state.json"
    if not live_path.exists():
        raise HTTPException(status_code=404, detail="No active session")

    try:
        live = json.loads(live_path.read_text(encoding="utf-8"))
        # Check for a screenshot path written by the harness
        screenshot_path = live.get("last_screenshot")
        if screenshot_path and Path(screenshot_path).exists():
            import base64
            data = base64.b64encode(Path(screenshot_path).read_bytes()).decode()
            return {"mime": "image/png", "data": data, "ts": live.get("last_update_ts")}
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="No screenshot available")


# ---------------------------------------------------------------------------
# WebSocket live state (#66) — push events instead of polling
# ---------------------------------------------------------------------------

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """
    Push live_state updates to the Studio every 1.5s instead of polling.
    Clients connect once and receive JSON frames until disconnect.
    """
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            # Load live state
            def _read_live():
                live_path = Path(_store_dir) / "_live_state.json"
                if not live_path.exists():
                    return {"isWorkerRunning": False}
                try:
                    return json.loads(live_path.read_text(encoding="utf-8"))
                except Exception:
                    return {"isWorkerRunning": False}

            live = await asyncio.to_thread(_read_live)
            await websocket.send_json(live)
            await asyncio.sleep(1.2)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            _ws_clients.remove(websocket)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Corpus endpoints (#92)
# ---------------------------------------------------------------------------

@app.get("/api/corpus/stats")
async def corpus_stats_endpoint():
    def _load():
        from browsermind_core.mission.corpus_stats import CorpusStats
        cs = CorpusStats(Path(_store_dir))
        return {
            "queue":       cs.queue_summary(),
            "hypotheses":  cs.hypothesis_summary(),
            "freshness":   cs.freshness_summary(),
            "coverage":    cs.site_coverage_summary(),
            "cross_site":  cs.cross_site_summary(),     # (#37)
        }
    return await asyncio.to_thread(_load)


# ---------------------------------------------------------------------------
# Site registry endpoints (#44)
# ---------------------------------------------------------------------------

@app.get("/api/sites")
async def sites_list(
    category: Optional[str] = None,
    max_difficulty: int = 5,
    limit: int = 100,
):
    def _load():
        from browsermind_core.mission.site_registry import list_sites
        specs = list_sites(category=category, max_difficulty=max_difficulty)[:limit]
        return [
            {
                "key":          s.key,
                "start_url":    s.start_url,
                "category":     s.category,
                "difficulty":   s.difficulty,
                "description":  s.description,
                "requires_login": s.requires_login,
                "tags":         s.tags,
            }
            for s in specs
        ]
    return await asyncio.to_thread(_load)


@app.get("/api/sites/categories")
async def sites_categories():
    from browsermind_core.mission.site_registry import SITE_CATEGORIES
    return SITE_CATEGORIES


@app.get("/api/sites/{site_key}/validate")
async def sites_validate(site_key: str):
    """Quick availability check — does not launch a real browser."""
    def _check():
        from browsermind_core.mission.site_registry import get_spec, resolve_site
        from browsermind_core.runtime.environment_registry import resolve
        env = resolve(site_key) or resolve_site(site_key)
        spec = get_spec(site_key)
        if env is None:
            return {"found": False, "site_key": site_key}
        return {
            "found":          True,
            "site_key":       site_key,
            "start_url":      env.start_url,
            "category":       spec.category if spec else env.family,
            "difficulty":     spec.difficulty if spec else None,
            "requires_login": spec.requires_login if spec else False,
        }
    return await asyncio.to_thread(_check)


# ---------------------------------------------------------------------------
# Mission run rate-limiting (#68)
# ---------------------------------------------------------------------------

# Override /api/missions/run to add rate limiting
_MISSION_RUN_COOLDOWN_S = 5.0  # minimum seconds between start-worker calls


@app.post("/api/missions/run-safe")
async def missions_run_safe(body: "MissionRunBody"):  # type: ignore[name-defined]
    """Rate-limited version of /api/missions/run."""
    global _mission_run_last_ts
    now = _time.time()
    if now - _mission_run_last_ts < _MISSION_RUN_COOLDOWN_S:
        remaining = _MISSION_RUN_COOLDOWN_S - (now - _mission_run_last_ts)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited — wait {remaining:.1f}s before starting another worker",
        )
    _mission_run_last_ts = now
    return await missions_run(body)  # type: ignore[name-defined]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


# =============================================================================
# /api/sessions — Session Manager endpoints
# =============================================================================

@app.get("/api/sessions")
async def sessions_list(persona: Optional[str] = None):
    """List all saved browser sessions with metadata."""
    def _load():
        from browsermind_core.session.session_manager import SessionManager
        mgr = SessionManager(Path(_store_dir))
        return [s.to_dict() for s in mgr.list_sessions(persona=persona)]
    return await asyncio.to_thread(_load)


@app.get("/api/sessions/{persona}/{site_key}")
async def sessions_get(persona: str, site_key: str):
    """Get metadata for a single (persona, site) session."""
    def _load():
        from browsermind_core.session.session_manager import SessionManager
        mgr = SessionManager(Path(_store_dir))
        meta = mgr.get_session(site_key, persona)
        if meta is None:
            return None
        return meta.to_dict()
    result = await asyncio.to_thread(_load)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No session for {persona}/{site_key}")
    return result


@app.post("/api/sessions/{persona}/{site_key}/mark-logged-in")
async def sessions_mark_logged_in(persona: str, site_key: str):
    """Mark a session as logged_in (call after manual login)."""
    def _mark():
        from browsermind_core.session.session_manager import SessionManager
        mgr = SessionManager(Path(_store_dir))
        meta = mgr.mark_logged_in(site_key, persona)
        return meta.to_dict()
    return await asyncio.to_thread(_mark)


@app.post("/api/sessions/{persona}/{site_key}/mark-expired")
async def sessions_mark_expired(persona: str, site_key: str):
    """Mark a session as expired."""
    def _mark():
        from browsermind_core.session.session_manager import SessionManager
        mgr = SessionManager(Path(_store_dir))
        meta = mgr.mark_expired(site_key, persona)
        return meta.to_dict()
    return await asyncio.to_thread(_mark)


@app.post("/api/sessions/{persona}/{site_key}/refresh")
async def sessions_refresh(persona: str, site_key: str):
    """Recompute cookie count and storage size for a session."""
    def _refresh():
        from browsermind_core.session.session_manager import SessionManager
        mgr = SessionManager(Path(_store_dir))
        meta = mgr.refresh_metadata(site_key, persona)
        return meta.to_dict()
    return await asyncio.to_thread(_refresh)


def main():
    import signal
    global _store_dir

    parser = argparse.ArgumentParser(description="BrowserMind API Sidecar")
    parser.add_argument("--port", type=int, default=8766, help="Port to bind on (default: 8766)")
    parser.add_argument("--store", type=str, default=DEFAULT_STORE, help="Store directory path")
    args = parser.parse_args()

    _store_dir = args.store
    port = args.port

    if _port_in_use(port):
        print(f"ERROR:port {port} already in use — another sidecar instance may be running", flush=True)
        sys.exit(1)

    def _handle_sigterm(signum, frame):
        print("SIGTERM received — shutting down", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    class _ReadyServer(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            # Signal to the Rust host that we're ready
            print(f"READY:{port}", flush=True)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = _ReadyServer(config)
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
