"""knowledge graph nodes and edges

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("properties", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("qdrant_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "node_type", "label", name="uq_node_project_type_label"),
    )
    op.create_index("ix_knowledge_nodes_project_id", "knowledge_nodes", ["project_id"])
    op.create_index("ix_knowledge_nodes_type", "knowledge_nodes", ["node_type"])

    op.create_table(
        "knowledge_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation", sa.String(50), nullable=False),
        sa.Column("properties", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "target_id", "relation", name="uq_edge_source_target_rel"),
    )
    op.create_index("ix_knowledge_edges_source", "knowledge_edges", ["source_id"])
    op.create_index("ix_knowledge_edges_target", "knowledge_edges", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_edges_target", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_source", table_name="knowledge_edges")
    op.drop_table("knowledge_edges")
    op.drop_index("ix_knowledge_nodes_type", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_project_id", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
