"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("celery_task_id", sa.String(255), nullable=False),
        sa.Column("ticket_id", sa.String(50), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("labels", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("repository", sa.Text, nullable=False),
        sa.Column("branch_base", sa.String(100), nullable=False, server_default="develop"),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("pull_request_url", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("analysis", postgresql.JSON, nullable=True),
        sa.Column("plan", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("celery_task_id"),
    )
    op.create_index("ix_pipeline_runs_ticket_id", "pipeline_runs", ["ticket_id"])

    op.create_table(
        "agent_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="success"),
        sa.Column("output", postgresql.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_results")
    op.drop_index("ix_pipeline_runs_ticket_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
