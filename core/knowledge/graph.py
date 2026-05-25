import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.knowledge.models import EdgeRelation, KnowledgeEdge, KnowledgeNode, NodeType

log = structlog.get_logger()


@dataclass
class NodeData:
    id: uuid.UUID
    node_type: str
    label: str
    description: str
    properties: dict


@dataclass
class EdgeData:
    source_label: str
    target_label: str
    relation: str
    properties: dict


class KnowledgeGraph:
    def __init__(self, session: AsyncSession, project_id: str) -> None:
        self._session = session
        self._project_id = project_id

    async def get_or_create_node(
        self,
        node_type: NodeType,
        label: str,
        description: str = "",
        properties: dict | None = None,
        qdrant_id: str | None = None,
    ) -> KnowledgeNode:
        result = await self._session.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.project_id == self._project_id,
                KnowledgeNode.node_type == node_type.value,
                KnowledgeNode.label == label,
            )
        )
        node = result.scalar_one_or_none()

        if node is None:
            node = KnowledgeNode(
                project_id=self._project_id,
                node_type=node_type.value,
                label=label,
                description=description,
                properties=properties or {},
                qdrant_id=qdrant_id,
            )
            self._session.add(node)
            await self._session.flush()
            log.info("knowledge_node_created", type=node_type.value, label=label)
        else:
            if description and not node.description:
                node.description = description
            if properties:
                node.properties = {**node.properties, **properties}

        return node

    async def add_edge(
        self,
        source: KnowledgeNode,
        target: KnowledgeNode,
        relation: EdgeRelation,
        properties: dict | None = None,
    ) -> KnowledgeEdge:
        result = await self._session.execute(
            select(KnowledgeEdge).where(
                KnowledgeEdge.source_id == source.id,
                KnowledgeEdge.target_id == target.id,
                KnowledgeEdge.relation == relation.value,
            )
        )
        edge = result.scalar_one_or_none()

        if edge is None:
            edge = KnowledgeEdge(
                source_id=source.id,
                target_id=target.id,
                relation=relation.value,
                properties=properties or {},
            )
            self._session.add(edge)
            await self._session.flush()

        return edge

    async def get_neighbors(
        self,
        label: str,
        node_type: NodeType,
        relation: EdgeRelation | None = None,
        depth: int = 1,
    ) -> list[NodeData]:
        result = await self._session.execute(
            select(KnowledgeNode)
            .where(
                KnowledgeNode.project_id == self._project_id,
                KnowledgeNode.node_type == node_type.value,
                KnowledgeNode.label == label,
            )
            .options(selectinload(KnowledgeNode.outgoing).selectinload(KnowledgeEdge.target))
        )
        node = result.scalar_one_or_none()
        if not node:
            return []

        neighbors: list[NodeData] = []
        for edge in node.outgoing:
            if relation and edge.relation != relation.value:
                continue
            neighbors.append(
                NodeData(
                    id=edge.target.id,
                    node_type=edge.target.node_type,
                    label=edge.target.label,
                    description=edge.target.description,
                    properties=edge.target.properties,
                )
            )
        return neighbors

    async def get_similar_fixes(self, ticket_type: str, files: list[str]) -> list[NodeData]:
        result = await self._session.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.project_id == self._project_id,
                KnowledgeNode.node_type == NodeType.FIX.value,
            )
        )
        all_fixes = list(result.scalars().all())

        scored: list[tuple[float, KnowledgeNode]] = []
        for fix in all_fixes:
            score = 0.0
            if fix.properties.get("ticket_type") == ticket_type:
                score += 2.0
            fix_files: list[str] = fix.properties.get("files_changed", [])
            overlap = len(set(files) & set(fix_files))
            score += overlap * 1.5
            if score > 0:
                scored.append((score, fix))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            NodeData(
                id=f.id,
                node_type=f.node_type,
                label=f.label,
                description=f.description,
                properties=f.properties,
            )
            for _, f in scored[:5]
        ]

    async def get_file_context(self, file_path: str) -> dict:
        deps = await self.get_neighbors(file_path, NodeType.FILE, EdgeRelation.DEPENDS_ON)
        services = await self.get_neighbors(file_path, NodeType.FILE, EdgeRelation.BELONGS_TO)
        patterns = await self.get_neighbors(file_path, NodeType.FILE, EdgeRelation.USES_PATTERN)
        return {
            "dependencies": [d.label for d in deps],
            "services": [s.label for s in services],
            "patterns": [p.label for p in patterns],
        }

    async def list_nodes(self, node_type: NodeType) -> list[NodeData]:
        result = await self._session.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.project_id == self._project_id,
                KnowledgeNode.node_type == node_type.value,
            )
        )
        return [
            NodeData(id=n.id, node_type=n.node_type, label=n.label, description=n.description, properties=n.properties)
            for n in result.scalars().all()
        ]
