from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.ticket import PipelineStatus, TaskStatusResponse
from core.database import get_db
from core.repositories import PipelineRunRepository

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/history/{ticket_id}", response_model=list[TaskStatusResponse])
async def ticket_history(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[TaskStatusResponse]:
    repo = PipelineRunRepository(db)
    runs = await repo.get_by_ticket_id(ticket_id)
    return [
        TaskStatusResponse(
            task_id=str(run.celery_task_id),
            ticket_id=run.ticket_id,
            status=PipelineStatus(run.status),
            pull_request_url=run.pull_request_url,
            branch_name=run.branch_name,
            error=run.error,
        )
        for run in runs
    ]
