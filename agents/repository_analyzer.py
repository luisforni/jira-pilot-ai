from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from api.models.ticket import TicketAnalysis
from core.config import settings

_EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
_TEXT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rb", ".rs",
    ".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".env.example",
    ".sh", ".sql", ".html", ".css", ".scss",
}
_MAX_FILE_SIZE = 50_000  # bytes


def _collect_repo_context(repo_path: Path, max_chars: int = 80_000) -> str:
    collected: list[str] = []
    total = 0

    for path in sorted(repo_path.rglob("*")):
        if any(excluded in path.parts for excluded in _EXCLUDED_DIRS):
            continue
        if not path.is_file():
            continue
        if path.suffix not in _TEXT_EXTENSIONS:
            continue
        if path.stat().st_size > _MAX_FILE_SIZE:
            continue

        rel = path.relative_to(repo_path)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        chunk = f"### {rel}\n{content}\n"
        if total + len(chunk) > max_chars:
            break
        collected.append(chunk)
        total += len(chunk)

    return "\n".join(collected)


class RepositoryAnalyzerAgent:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
        )

    async def analyze(self, repo_path: Path, ticket_analysis: TicketAnalysis) -> str:
        context = _collect_repo_context(repo_path)

        system_prompt = """You are a senior software architect.
Given the repository code and a ticket analysis, identify:
1. The exact files that need to be modified
2. The architecture patterns used
3. Naming conventions
4. Testing patterns
5. Any relevant context for implementing the fix/feature

Be concise and focused on what the developer agent needs to implement the solution."""

        prompt = f"""Ticket analysis:
{ticket_analysis.model_dump_json(indent=2)}

Repository context:
{context}

Provide a focused technical context report for implementing this ticket."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]

        response = await self._llm.ainvoke(messages)
        return str(response.content)
