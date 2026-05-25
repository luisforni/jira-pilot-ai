import hashlib
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Request, status

from core.config import settings
from workers.celery_app import celery_app

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

AI_TRIGGER_LABELS = {"ai:auto-fix", "ai:backend", "ai:frontend", "ai:hotfix"}


def _verify_jira_signature(payload: bytes, signature: str) -> bool:
    secret = settings.n8n_webhook_secret.encode()
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/jira")
async def jira_webhook(
    request: Request,
    x_hub_signature: str = Header(default=""),
) -> dict:
    body = await request.body()

    # Validate signature if configured
    if settings.n8n_webhook_secret != "change-me-in-production" and x_hub_signature:
        sig = x_hub_signature.removeprefix("sha256=")
        if not _verify_jira_signature(body, sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("webhookEvent", "")

    # Only process assignment events
    if event not in ("jira:issue_updated", "jira:issue_created"):
        return {"status": "ignored", "event": event}

    issue = payload.get("issue", {})
    fields = issue.get("fields", {})
    labels: list[str] = fields.get("labels", [])
    assignee = fields.get("assignee") or {}

    ai_labels = AI_TRIGGER_LABELS.intersection(set(labels))
    if not ai_labels:
        return {"status": "ignored", "reason": "no AI trigger label"}

    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo_slug = os.environ.get("GITHUB_REPO_SLUG", "")
    repository = os.environ.get("PROJECT_REPOSITORY", "")

    if not repository:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PROJECT_REPOSITORY env var not configured",
        )

    task = celery_app.send_task(
        "workers.tasks.run_ticket_pipeline",
        kwargs={
            "ticket_id": issue.get("key", ""),
            "title": fields.get("summary", ""),
            "description": fields.get("description", "") or "",
            "labels": labels,
            "repository": repository,
            "branch_base": "develop",
            "github_token": github_token,
            "repo_slug": repo_slug,
            "assignee_account_id": assignee.get("accountId"),
        },
        queue="pipeline",
    )

    return {"status": "queued", "task_id": task.id, "ticket_id": issue.get("key")}
