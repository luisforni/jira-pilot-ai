import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from api.models.ticket import TicketAnalysis, TechnicalPlan
from core.config import settings

_SYSTEM_PROMPT = """You are a senior software engineer creating implementation plans.
Given a ticket analysis and repository context, produce a precise technical plan.

Respond ONLY with valid JSON:
{
  "steps": ["ordered list of implementation steps"],
  "files_to_modify": ["relative/path/to/file.py"],
  "files_to_create": ["relative/path/to/new_file.py"],
  "estimated_complexity": "low|medium|high"
}
"""


class PlannerAgent:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
        )

    async def plan(
        self,
        ticket_analysis: TicketAnalysis,
        repo_context: str,
        title: str,
        description: str,
    ) -> TechnicalPlan:
        prompt = f"""Ticket title: {title}
Description: {description}

Analysis:
{ticket_analysis.model_dump_json(indent=2)}

Repository context:
{repo_context}

Generate a detailed implementation plan."""

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = await self._llm.ainvoke(messages)
        raw = str(response.content).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        return TechnicalPlan(
            steps=data.get("steps", []),
            files_to_modify=data.get("files_to_modify", []),
            files_to_create=data.get("files_to_create", []),
            estimated_complexity=data.get("estimated_complexity", "medium"),
        )
