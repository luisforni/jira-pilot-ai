import uuid
from enum import Enum as PyEnum

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin


class NodeType(str, PyEnum):
    FILE = "file"
    SERVICE = "service"
    PATTERN = "pattern"
    FIX = "fix"


class EdgeRelation(str, PyEnum):
    DEPENDS_ON = "depends_on"
    BELONGS_TO = "belongs_to"
    FIXED_BY = "fixed_by"
    SIMILAR_TO = "similar_to"
    USES_PATTERN = "uses_pattern"
    CAUSED_BY = "caused_by"


class KnowledgeNode(Base, TimestampMixin):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        UniqueConstraint("project_id", "node_type", "label", name="uq_node_project_type_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    qdrant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    outgoing: Mapped[list["KnowledgeEdge"]] = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    incoming: Mapped[list["KnowledgeEdge"]] = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.target_id",
        back_populates="target",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeNode {self.node_type}:{self.label}>"


class KnowledgeEdge(Base, TimestampMixin):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation", name="uq_edge_source_target_rel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(50), nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)

    source: Mapped["KnowledgeNode"] = relationship("KnowledgeNode", foreign_keys=[source_id], back_populates="outgoing")
    target: Mapped["KnowledgeNode"] = relationship("KnowledgeNode", foreign_keys=[target_id], back_populates="incoming")

    def __repr__(self) -> str:
        return f"<KnowledgeEdge {self.relation}>"
