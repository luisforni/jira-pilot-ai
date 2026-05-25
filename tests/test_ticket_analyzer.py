from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.ticket_analyzer import TicketAnalyzerAgent
from api.models.ticket import RiskLevel, TicketType


@pytest.mark.asyncio
async def test_analyze_bug_ticket():
    mock_response = MagicMock()
    mock_response.content = """{
        "type": "bug",
        "files_probably_related": ["auth/service.py"],
        "risk": "medium",
        "stack": ["python", "fastapi"],
        "priority": "high",
        "summary": "Login timeout not handled correctly in auth service"
    }"""

    with patch("agents.ticket_analyzer.ChatAnthropic") as mock_llm_cls:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_response
        mock_llm_cls.return_value = mock_llm

        agent = TicketAnalyzerAgent()
        result = await agent.analyze(
            ticket_id="PROJ-145",
            title="Fix login timeout",
            description="Users are experiencing timeout errors on login",
            labels=["bug", "backend"],
        )

    assert result.type == TicketType.BUG
    assert result.risk == RiskLevel.MEDIUM
    assert "auth/service.py" in result.files_probably_related
    assert result.priority == "high"


@pytest.mark.asyncio
async def test_analyze_feature_ticket():
    mock_response = MagicMock()
    mock_response.content = """{
        "type": "feature",
        "files_probably_related": [],
        "risk": "low",
        "stack": ["python"],
        "priority": "medium",
        "summary": "Add export to CSV functionality"
    }"""

    with patch("agents.ticket_analyzer.ChatAnthropic") as mock_llm_cls:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_response
        mock_llm_cls.return_value = mock_llm

        agent = TicketAnalyzerAgent()
        result = await agent.analyze(
            ticket_id="PROJ-200",
            title="Add CSV export",
            description="Users need to export data as CSV",
            labels=["feature"],
        )

    assert result.type == TicketType.FEATURE
    assert result.risk == RiskLevel.LOW
