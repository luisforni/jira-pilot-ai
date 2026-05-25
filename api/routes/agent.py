import os

from fastapi import APIRouter, Depends, status

from api.models.ticket import (
    PipelineStatus,
    RunTicketRequest,
    RunTicketResponse,
    TaskStatusResponse,
)
from core.auth.deps import get_org_from_api_key, require_pipeline_quota
from core.auth.rate_limit import get_usage
from core.models.auth import PLAN_MONTHLY_LIMITS, Organization
from workers.celery_app import celery_app

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run-ticket", response_model=RunTicketResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_ticket(
    body: RunTicketRequest,
    org: Organization = Depends(require_pipeline_quota),
) -> RunTicketResponse:
    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo_slug = os.environ.get("GITHUB_REPO_SLUG", "")

    task = celery_app.send_task(
        "workers.tasks.run_ticket_pipeline",
        kwargs={
            "org_id": str(org.id),
            "ticket_id": body.ticket_id,
            "title": body.title,
            "description": body.description,
            "labels": body.labels,
            "repository": body.repository,
            "branch_base": body.branch_base,
            "github_token": github_token,
            "repo_slug": repo_slug,
            "assignee_account_id": body.assignee_account_id,
        },
        queue="pipeline",
    )

    return RunTicketResponse(
        task_id=task.id,
        ticket_id=body.ticket_id,
        status=PipelineStatus.QUEUED,
        message="Pipeline queued successfully",
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    _org: Organization = Depends(get_org_from_api_key),
) -> TaskStatusResponse:
    result = celery_app.AsyncResult(task_id)

    if result.state == "PENDING":
        return TaskStatusResponse(task_id=task_id, ticket_id="", status=PipelineStatus.QUEUED)
    if result.state == "STARTED":
        return TaskStatusResponse(task_id=task_id, ticket_id="", status=PipelineStatus.ANALYZING)
    if result.state == "FAILURE":
        return TaskStatusResponse(task_id=task_id, ticket_id="", status=PipelineStatus.FAILED, error=str(result.result))

    data = result.result or {}
    return TaskStatusResponse(
        task_id=task_id,
        ticket_id="",
        status=PipelineStatus(data.get("status", PipelineStatus.COMPLETED)),
        pull_request_url=data.get("pull_request_url"),
        branch_name=data.get("branch_name"),
        error=data.get("error"),
    )


@router.get("/quota", tags=["agent"])
async def get_quota(org: Organization = Depends(get_org_from_api_key)) -> dict:
    usage = await get_usage(str(org.id))
    limit = PLAN_MONTHLY_LIMITS.get(org.plan, 50)
    return {
        "org_slug": org.slug,
        "plan": org.plan,
        "usage_this_month": usage,
        "monthly_limit": limit,
        "remaining": max(0, limit - usage),
    }
