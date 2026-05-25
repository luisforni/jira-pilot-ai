import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.pipeline import AgentResult, PipelineRun


class PipelineRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        celery_task_id: str,
        ticket_id: str,
        title: str,
        description: str,
        labels: list[str],
        repository: str,
        branch_base: str,
    ) -> PipelineRun:
        run = PipelineRun(
            celery_task_id=celery_task_id,
            ticket_id=ticket_id,
            title=title,
            description=description,
            labels=labels,
            repository=repository,
            branch_base=branch_base,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_by_task_id(self, celery_task_id: str) -> PipelineRun | None:
        result = await self._session.execute(
            select(PipelineRun).where(PipelineRun.celery_task_id == celery_task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_ticket_id(self, ticket_id: str) -> list[PipelineRun]:
        result = await self._session.execute(
            select(PipelineRun)
            .where(PipelineRun.ticket_id == ticket_id)
            .order_by(PipelineRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        **kwargs,
    ) -> None:
        run = await self._session.get(PipelineRun, run_id)
        if run:
            run.status = status
            run.updated_at = datetime.now(timezone.utc)
            for key, value in kwargs.items():
                setattr(run, key, value)

    async def add_agent_result(
        self,
        run_id: uuid.UUID,
        agent_name: str,
        status: str = "success",
        output: dict | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> AgentResult:
        result = AgentResult(
            pipeline_run_id=run_id,
            agent_name=agent_name,
            status=status,
            output=output,
            error=error,
            duration_ms=duration_ms,
        )
        self._session.add(result)
        await self._session.flush()
        return result
