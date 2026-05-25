from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.knowledge.memory import ProjectMemory, project_id_from_repo
from core.knowledge.models import NodeType


def test_project_id_from_repo_deterministic():
    repo = "git@github.com:company/api.git"
    assert project_id_from_repo(repo) == project_id_from_repo(repo)
    assert len(project_id_from_repo(repo)) == 16


def test_project_id_differs_per_repo():
    id1 = project_id_from_repo("git@github.com:company/api.git")
    id2 = project_id_from_repo("git@github.com:company/frontend.git")
    assert id1 != id2


@pytest.mark.asyncio
async def test_project_memory_empty_returns_empty_string():
    mock_session = AsyncMock()
    mock_graph = AsyncMock()
    mock_graph.get_similar_fixes.return_value = []
    mock_graph.get_file_context.return_value = {"dependencies": [], "services": [], "patterns": []}
    mock_graph.list_nodes.return_value = []

    with patch("core.knowledge.memory.KnowledgeGraph", return_value=mock_graph):
        memory = ProjectMemory(mock_session, "proj-abc123")
        result = await memory.get_context_for_ticket(
            ticket_type="bug",
            files_hint=["auth/service.py"],
            title="Fix login",
        )

    assert result == ""


@pytest.mark.asyncio
async def test_project_memory_with_fixes():
    from core.knowledge.graph import NodeData
    import uuid

    mock_session = AsyncMock()
    mock_graph = AsyncMock()
    mock_graph.get_similar_fixes.return_value = [
        NodeData(
            id=uuid.uuid4(),
            node_type="fix",
            label="PROJ-100: previous auth fix",
            description="Fixed session expiry handling",
            properties={
                "ticket_id": "PROJ-100",
                "ticket_type": "bug",
                "files_changed": ["auth/service.py"],
                "pr_url": "https://github.com/company/api/pull/42",
            },
        )
    ]
    mock_graph.get_file_context.return_value = {"dependencies": [], "services": [], "patterns": []}
    mock_graph.list_nodes.return_value = []

    with patch("core.knowledge.memory.KnowledgeGraph", return_value=mock_graph):
        memory = ProjectMemory(mock_session, "proj-abc123")
        result = await memory.get_context_for_ticket(
            ticket_type="bug",
            files_hint=["auth/service.py"],
            title="Fix login timeout",
        )

    assert "PROJ-100" in result
    assert "Similar past fixes" in result
