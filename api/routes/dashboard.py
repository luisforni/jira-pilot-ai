from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.repositories import PipelineRunRepository

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="dashboard/templates")

STATUS_COLORS = {
    "queued": "gray",
    "analyzing": "blue",
    "planning": "indigo",
    "developing": "yellow",
    "testing": "orange",
    "reviewing": "purple",
    "pr_created": "green",
    "completed": "green",
    "failed": "red",
}

AGENT_LABELS = {
    "ticket_analyzer": "Ticket Analyzer",
    "project_memory": "Project Memory",
    "repository_analyzer": "Repo Analyzer",
    "planner": "Planner",
    "developer": "Developer",
    "qa_agent": "QA",
    "reviewer": "Reviewer",
    "devops_agent": "DevOps",
}

AGENT_ORDER = list(AGENT_LABELS.keys())


def _enrich_run(run) -> dict:
    agents_map = {a.agent_name: a for a in (run.agent_results or [])}
    agents = []
    for name in AGENT_ORDER:
        a = agents_map.get(name)
        agents.append({
            "name": name,
            "label": AGENT_LABELS.get(name, name),
            "status": a.status if a else "pending",
            "duration_ms": a.duration_ms if a else None,
            "error": a.error if a else None,
        })
    return {
        "task_id": run.celery_task_id,
        "ticket_id": run.ticket_id,
        "title": run.title,
        "status": run.status,
        "color": STATUS_COLORS.get(run.status, "gray"),
        "pull_request_url": run.pull_request_url,
        "branch_name": run.branch_name,
        "error": run.error,
        "created_at": run.created_at.strftime("%Y-%m-%d %H:%M") if run.created_at else "",
        "agents": agents,
    }


@router.get("", response_class=HTMLResponse)
async def dashboard_index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    repo = PipelineRunRepository(db)
    runs = await repo.list_recent(50)
    summary = await repo.status_summary()

    enriched = [_enrich_run(r) for r in runs]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "runs": enriched,
            "summary": summary,
            "total": sum(summary.values()),
        },
    )


@router.get("/pipeline/{task_id}", response_class=HTMLResponse)
async def pipeline_detail(request: Request, task_id: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    repo = PipelineRunRepository(db)
    run = await repo.get_with_agents(task_id)
    if not run:
        return HTMLResponse("<h1>Pipeline not found</h1>", status_code=404)

    enriched = _enrich_run(run)
    return templates.TemplateResponse(
        "pipeline_detail.html",
        {"request": request, "run": enriched},
    )


@router.get("/metrics", response_class=HTMLResponse)
async def metrics(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    repo = PipelineRunRepository(db)
    agent_metrics = await repo.agent_metrics()
    summary = await repo.status_summary()

    for m in agent_metrics:
        m["label"] = AGENT_LABELS.get(m["agent"], m["agent"])

    return templates.TemplateResponse(
        "metrics.html",
        {"request": request, "agent_metrics": agent_metrics, "summary": summary},
    )


@router.get("/graph", response_class=HTMLResponse)
async def graph_view(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("graph.html", {"request": request})
