from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from api.models.ticket import TicketAnalysis, TechnicalPlan
from core.config import settings

_SYSTEM_PROMPT = """You are an expert software developer implementing Jira tickets.
For each file that needs to be modified or created, output the complete file content.

Use this exact format for each file:
<<<FILE: relative/path/to/file.py>>>
<complete file content here>
<<<END_FILE>>>

Follow the existing code style, patterns, and conventions found in the repository.
Do NOT include explanations outside the file blocks.
"""


def _parse_file_blocks(raw: str) -> dict[str, str]:
    files: dict[str, str] = {}
    parts = raw.split("<<<FILE:")
    for part in parts[1:]:
        if ">>>" not in part:
            continue
        header, _, rest = part.partition(">>>")
        file_path = header.strip()
        content, _, _ = rest.partition("<<<END_FILE>>>")
        files[file_path] = content.lstrip("\n")
    return files


class DeveloperAgent:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=8192,
        )

    async def implement(
        self,
        repo_path: Path,
        plan: TechnicalPlan,
        ticket_analysis: TicketAnalysis,
        repo_context: str,
        title: str,
        description: str,
    ) -> list[str]:
        files_content: dict[str, str] = {}
        for file_path in plan.files_to_modify:
            full_path = repo_path / file_path
            if full_path.exists():
                try:
                    files_content[file_path] = full_path.read_text(encoding="utf-8")
                except OSError:
                    pass

        existing = "\n".join(
            f"### {k}\n{v}" for k, v in files_content.items()
        )

        prompt = f"""Ticket: {title}
Description: {description}

Technical plan:
{plan.model_dump_json(indent=2)}

Analysis:
{ticket_analysis.model_dump_json(indent=2)}

Repository context:
{repo_context}

Current file contents:
{existing}

Implement ALL changes described in the plan. Output complete file contents."""

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = await self._llm.ainvoke(messages)
        generated = _parse_file_blocks(str(response.content))

        modified: list[str] = []
        for rel_path, content in generated.items():
            full_path = repo_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            modified.append(rel_path)

        return modified
