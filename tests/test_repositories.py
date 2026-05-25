import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.repositories import PipelineRunRepository


@pytest.mark.asyncio
async def test_create_pipeline_run():
    mock_session = AsyncMock()
    mock_run = MagicMock()
    mock_run.id = uuid.uuid4()
    mock_session.flush = AsyncMock()

    repo = PipelineRunRepository(mock_session)

    with patch.object(repo._session, "add") as mock_add:
        mock_add.return_value = None
        mock_session.flush.return_value = None

        run = await repo.create(
            celery_task_id="task-123",
            ticket_id="PROJ-145",
            title="Fix login timeout",
            description="Users see 30s timeout",
            labels=["bug"],
            repository="git@github.com:company/api.git",
            branch_base="develop",
        )

    mock_add.assert_called_once()
    assert mock_session.flush.called


@pytest.mark.asyncio
async def test_get_by_ticket_id_empty():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = PipelineRunRepository(mock_session)
    runs = await repo.get_by_ticket_id("PROJ-999")

    assert runs == []
