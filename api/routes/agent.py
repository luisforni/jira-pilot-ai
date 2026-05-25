import os

from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.models.ticket import (
    PipelineStatus,
    RunTicketRequest,
    RunTicketResponse,
    TaskStatusResponse,
)
from core.config import settings
from workers.celery_app import celery_app

router = APIRouter(prefix="/agent", tags=["agent"])


def _verify_webhook_secret(x_webhook_secret: str = Header(...)) -> None:
    if x_webhook_secret != settings.n8n_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")


@router.post("/run-ticket", response_model=RunTicketResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_ticket(
    body: RunTicketRequest,
    _: None = Depends(_verify_webhook_secret),
) -> RunTicketResponse:
    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo_slug = os.environ.get("GITHUB_REPO_SLUG", "")

    task = celery_app.send_task(
        "workers.tasks.run_ticket_pipeline",
        kwargs={
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
async def get_task_status(task_id: str) -> TaskStatusResponse:
    result = celery_app.AsyncResult(task_id)

    if result.state == "PENDING":
        return TaskStatusResponse(
            task_id=task_id,
            ticket_id="",
            status=PipelineStatus.QUEUED,
        )

    if result.state == "STARTED":
        return TaskStatusResponse(
            task_id=task_id,
            ticket_id="",
            status=PipelineStatus.ANALYZING,
        )

    if result.state == "FAILURE":
        return TaskStatusResponse(
            task_id=task_id,
            ticket_id="",
            status=PipelineStatus.FAILED,
            error=str(result.result),
        )

    data = result.result or {}
    return TaskStatusResponse(
        task_id=task_id,
        ticket_id="",
        status=PipelineStatus(data.get("status", PipelineStatus.COMPLETED)),
        pull_request_url=data.get("pull_request_url"),
        branch_name=data.get("branch_name"),
        error=data.get("error"),
    )
