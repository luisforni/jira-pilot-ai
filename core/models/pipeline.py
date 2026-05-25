import uuid

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin


class PipelineRun(Base, TimestampMixin):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    celery_task_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ticket_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[list] = mapped_column(JSON, default=list)
    repository: Mapped[str] = mapped_column(Text, nullable=False)
    branch_base: Mapped[str] = mapped_column(String(100), default="develop")
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    pull_request_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    agent_results: Mapped[list["AgentResult"]] = relationship(
        "AgentResult", back_populates="pipeline_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PipelineRun {self.ticket_id} [{self.status}]>"


class AgentResult(Base, TimestampMixin):
    __tablename__ = "agent_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="success")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)

    pipeline_run: Mapped["PipelineRun"] = relationship(
        "PipelineRun", back_populates="agent_results"
    )

    def __repr__(self) -> str:
        return f"<AgentResult {self.agent_name} [{self.status}]>"
