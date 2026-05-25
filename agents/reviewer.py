from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agents.qa_agent import QAResult
from api.models.ticket import TechnicalPlan
from core.config import settings

_SYSTEM_PROMPT = """You are a senior code reviewer performing a final review before PR creation.
Analyze the implementation against the plan and QA results.

Respond with JSON:
{
  "approved": true|false,
  "blocking_issues": ["list of issues that must be fixed before merging"],
  "suggestions": ["non-blocking improvement suggestions"],
  "security_concerns": ["any security issues found"],
  "summary": "brief review summary"
}
"""


class ReviewResult:
    def __init__(
        self,
        approved: bool,
        blocking_issues: list[str],
        suggestions: list[str],
        security_concerns: list[str],
        summary: str,
    ) -> None:
        self.approved = approved
        self.blocking_issues = blocking_issues
        self.suggestions = suggestions
        self.security_concerns = security_concerns
        self.summary = summary

    def to_pr_comment(self) -> str:
        lines = ["## AI Code Review\n"]
        lines.append(f"**Status**: {'✅ Approved' if self.approved else '❌ Changes requested'}\n")
        lines.append(f"**Summary**: {self.summary}\n")

        if self.blocking_issues:
            lines.append("\n### Blocking Issues")
            lines.extend(f"- {i}" for i in self.blocking_issues)

        if self.security_concerns:
            lines.append("\n### Security Concerns")
            lines.extend(f"- {c}" for c in self.security_concerns)

        if self.suggestions:
            lines.append("\n### Suggestions")
            lines.extend(f"- {s}" for s in self.suggestions)

        return "\n".join(lines)


class ReviewerAgent:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
        )

    async def review(
        self,
        plan: TechnicalPlan,
        modified_files: list[str],
        qa_result: QAResult,
        diff: str,
    ) -> ReviewResult:
        import json

        prompt = f"""Technical plan:
{plan.model_dump_json(indent=2)}

Modified files: {modified_files}

QA Result:
{qa_result.to_summary()}

Git diff:
{diff[:8000]}

Perform a thorough code review."""

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

        return ReviewResult(
            approved=data.get("approved", False),
            blocking_issues=data.get("blocking_issues", []),
            suggestions=data.get("suggestions", []),
            security_concerns=data.get("security_concerns", []),
            summary=data.get("summary", ""),
        )
