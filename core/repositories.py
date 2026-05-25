import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    async def list_recent(self, limit: int = 50) -> list[PipelineRun]:
        result = await self._session.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.agent_results))
            .order_by(PipelineRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_with_agents(self, celery_task_id: str) -> PipelineRun | None:
        result = await self._session.execute(
            select(PipelineRun)
            .where(PipelineRun.celery_task_id == celery_task_id)
            .options(selectinload(PipelineRun.agent_results))
        )
        return result.scalar_one_or_none()

    async def agent_metrics(self) -> list[dict]:
        result = await self._session.execute(
            select(
                AgentResult.agent_name,
                func.count(AgentResult.id).label("total"),
                func.avg(AgentResult.duration_ms).label("avg_ms"),
                func.sum(
                    func.cast(AgentResult.status == "success", func.Integer)
                ).label("successes"),
            ).group_by(AgentResult.agent_name)
        )
        rows = result.all()
        return [
            {
                "agent": r.agent_name,
                "total": r.total,
                "avg_ms": round(r.avg_ms or 0),
                "success_rate": round((r.successes or 0) / r.total * 100, 1),
            }
            for r in rows
        ]

    async def status_summary(self) -> dict[str, int]:
        result = await self._session.execute(
            select(PipelineRun.status, func.count(PipelineRun.id)).group_by(PipelineRun.status)
        )
        return {row[0]: row[1] for row in result.all()}
