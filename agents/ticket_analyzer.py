from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from api.models.ticket import RiskLevel, TicketAnalysis, TicketType
from core.config import settings

_SYSTEM_PROMPT = """You are a senior software engineer and technical analyst.
Analyze the given Jira ticket and return a structured JSON analysis.

Respond ONLY with valid JSON matching this schema:
{
  "type": "bug|feature|refactor|hotfix|task",
  "files_probably_related": ["list", "of", "file", "paths"],
  "risk": "low|medium|high",
  "stack": ["python", "react", "postgresql", ...],
  "priority": "low|medium|high|critical",
  "summary": "one sentence technical summary"
}
"""


class TicketAnalyzerAgent:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=1024,
        )

    async def analyze(
        self,
        ticket_id: str,
        title: str,
        description: str,
        labels: list[str],
    ) -> TicketAnalysis:
        prompt = f"""Ticket ID: {ticket_id}
Title: {title}
Description: {description}
Labels: {", ".join(labels)}

Analyze this ticket and return the JSON analysis."""

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = await self._llm.ainvoke(messages)
        import json

        raw = str(response.content).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        return TicketAnalysis(
            type=TicketType(data.get("type", "task")),
            files_probably_related=data.get("files_probably_related", []),
            risk=RiskLevel(data.get("risk", "medium")),
            stack=data.get("stack", []),
            priority=data.get("priority", "medium"),
            summary=data.get("summary", ""),
        )
