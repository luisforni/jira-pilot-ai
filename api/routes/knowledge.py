from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.knowledge.graph import KnowledgeGraph, NodeData
from core.knowledge.memory import ProjectMemory, project_id_from_repo
from core.knowledge.models import NodeType

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class ProjectGraphResponse(BaseModel):
    project_id: str
    files: list[dict]
    services: list[dict]
    patterns: list[dict]
    fixes: list[dict]


class MemoryContextResponse(BaseModel):
    project_id: str
    context: str


def _node_to_dict(n: NodeData) -> dict:
    return {
        "id": str(n.id),
        "label": n.label,
        "description": n.description,
        "properties": n.properties,
    }


@router.get("/graph/{repository:path}", response_model=ProjectGraphResponse)
async def get_project_graph(
    repository: str,
    db: AsyncSession = Depends(get_db),
) -> ProjectGraphResponse:
    project_id = project_id_from_repo(repository)
    graph = KnowledgeGraph(db, project_id)

    files = await graph.list_nodes(NodeType.FILE)
    services = await graph.list_nodes(NodeType.SERVICE)
    patterns = await graph.list_nodes(NodeType.PATTERN)
    fixes = await graph.list_nodes(NodeType.FIX)

    return ProjectGraphResponse(
        project_id=project_id,
        files=[_node_to_dict(n) for n in files],
        services=[_node_to_dict(n) for n in services],
        patterns=[_node_to_dict(n) for n in patterns],
        fixes=[_node_to_dict(n) for n in fixes],
    )


@router.get("/memory/{repository:path}", response_model=MemoryContextResponse)
async def get_project_memory(
    repository: str,
    ticket_type: str = "bug",
    db: AsyncSession = Depends(get_db),
) -> MemoryContextResponse:
    project_id = project_id_from_repo(repository)
    memory = ProjectMemory(db, project_id)
    context = await memory.get_context_for_ticket(
        ticket_type=ticket_type,
        files_hint=[],
        title="",
    )
    return MemoryContextResponse(project_id=project_id, context=context)
