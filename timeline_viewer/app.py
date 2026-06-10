"""FastAPI app for the Timeline Viewer.

Read-only observability over ~/.browsermind/outcome_ledger/. Localhost only.
Treat as instrumentation, not product UI.

UI Phase 1 — adds three view modes (failure-only, teacher-queue,
approval-queue) on the same primitive, plus a Live Workspace that polls
~/.browsermind/_live_state.json. The Approval Queue accepts approve/reject
POSTs that append to ~/.browsermind/approval_decisions.jsonl.

Run:
    python -m timeline_viewer.app
or:
    uvicorn timeline_viewer.app:app --port 8765
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from timeline_viewer.ledger_reader import (
    cascade_distribution,
    dyad_summary,
    get_execution,
    list_approval_decisions,
    list_executions,
    list_failed_executions,
    list_pending_approvals,
    list_teacher_queue_items,
    live_workspace_state,
    load_snapshots,
    overview_stats,
    record_approval_decision,
)

_THIS_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_THIS_DIR / "templates"))

app = FastAPI(title="BrowserMind Timeline Viewer", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_THIS_DIR / "static")), name="static")


# ── Execution browse (Stage 2 + Phase 1 view modes) ─────────────────────


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    env: Optional[str] = None,
    success: Optional[str] = None,
    template: Optional[str] = None,
):
    executions = list_executions()
    if env:
        executions = [e for e in executions if e["environment"] == env]
    if template:
        executions = [e for e in executions if e["template_name"] == template]
    if success == "yes":
        executions = [e for e in executions if e["overall_success"]]
    elif success == "no":
        executions = [e for e in executions if not e["overall_success"]]

    stats = overview_stats()
    pending_approvals_count = len(list_pending_approvals())
    teacher_queue = list_teacher_queue_items()
    teacher_queue_count = teacher_queue["total"] if isinstance(teacher_queue, dict) else 0
    all_envs = sorted({e["environment"] for e in list_executions() if e["environment"]})
    all_templates = sorted({e["template_name"] for e in list_executions() if e["template_name"]})

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "executions": executions,
            "stats": stats,
            "filters": {"env": env or "", "success": success or "", "template": template or ""},
            "all_envs": all_envs,
            "all_templates": all_templates,
            "pending_approvals_count": pending_approvals_count,
            "teacher_queue_count": teacher_queue_count,
        },
    )


@app.get("/execution/{execution_id}", response_class=HTMLResponse)
def execution_detail(request: Request, execution_id: str):
    detail = get_execution(execution_id)
    if not detail:
        raise HTTPException(status_code=404, detail="execution not found")
    return templates.TemplateResponse(request, "execution.html", {"detail": detail})


@app.get("/snapshots", response_class=HTMLResponse)
def snapshots_page(request: Request):
    rows = load_snapshots()
    return templates.TemplateResponse(request, "snapshots.html", {"rows": rows})


@app.get("/dyads", response_class=HTMLResponse)
def dyads_page(request: Request):
    rows = dyad_summary()
    cascade = cascade_distribution()
    return templates.TemplateResponse(
        request, "dyads.html", {"rows": rows, "cascade": cascade}
    )


# ── Phase 1 view modes ──────────────────────────────────────────────────


@app.get("/failures", response_class=HTMLResponse)
def failures_page(request: Request):
    """Failure-only view of the executions list — same primitive, filtered."""
    executions = list_failed_executions()
    stats = overview_stats()
    return templates.TemplateResponse(
        request,
        "failures.html",
        {
            "executions": executions,
            "stats": stats,
        },
    )


@app.get("/teacher", response_class=HTMLResponse)
def teacher_queue_page(request: Request):
    """Teacher Queue view — labels the resolver could not classify."""
    queue = list_teacher_queue_items()
    return templates.TemplateResponse(
        request, "teacher.html", {"queue": queue}
    )


@app.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request):
    """Approval Queue view — pending ASK decisions + audit trail."""
    pending = list_pending_approvals()
    decisions = list_approval_decisions(limit=50)
    return templates.TemplateResponse(
        request, "approvals.html",
        {"pending": pending, "decisions": decisions},
    )


@app.post("/approvals/decide")
def approvals_decide(
    execution_id: str = Form(...),
    step_seq: int = Form(...),
    decision: str = Form(...),
    reason: str = Form(""),
    operator: str = Form(""),
):
    try:
        row = record_approval_decision(
            execution_id=execution_id,
            step_seq=step_seq,
            decision=decision,
            reason=reason,
            operator=operator,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/approvals", status_code=303)


# ── Live Workspace ──────────────────────────────────────────────────────


@app.get("/live", response_class=HTMLResponse)
def live_workspace_page(request: Request):
    state = live_workspace_state()
    return templates.TemplateResponse(request, "live.html", {"state": state})


@app.get("/api/live")
def api_live():
    """Polled by the Live Workspace HTML page for refresh."""
    return JSONResponse(live_workspace_state())


# ── JSON APIs (existing + new) ──────────────────────────────────────────


@app.get("/api/dyads")
def api_dyads():
    return JSONResponse(dyad_summary())


@app.get("/api/cascade")
def api_cascade():
    return JSONResponse(cascade_distribution())


@app.get("/api/executions")
def api_executions():
    return JSONResponse(list_executions())


@app.get("/api/executions/{execution_id}")
def api_execution(execution_id: str):
    detail = get_execution(execution_id)
    if not detail:
        raise HTTPException(status_code=404, detail="execution not found")
    return JSONResponse(detail)


@app.get("/api/snapshots")
def api_snapshots():
    return JSONResponse(load_snapshots())


@app.get("/api/overview")
def api_overview():
    return JSONResponse(overview_stats())


@app.get("/api/failures")
def api_failures():
    return JSONResponse(list_failed_executions())


@app.get("/api/teacher")
def api_teacher():
    return JSONResponse(list_teacher_queue_items())


@app.get("/api/approvals")
def api_approvals():
    return JSONResponse({
        "pending": list_pending_approvals(),
        "decisions": list_approval_decisions(),
    })


def main() -> int:
    uvicorn.run(
        "timeline_viewer.app:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
