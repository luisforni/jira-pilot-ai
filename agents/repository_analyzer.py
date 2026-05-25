import hashlib
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from api.models.ticket import TicketAnalysis
from core.config import settings
from core.indexer import RepositoryIndexer
from core.rag import RAGRetriever

_SYSTEM_PROMPT = """You are a senior software architect performing repository analysis.
Given semantically retrieved code chunks and a ticket analysis, identify:
1. The exact files that need to be modified and why
2. Architecture patterns and naming conventions in use
3. Testing patterns (how tests are structured, what framework is used)
4. Any constraints or risks for implementing this ticket
5. Related utilities or helpers already available

Be concise. Focus only on what's relevant to implementing the given ticket."""


def _repo_id(repo_path: Path) -> str:
    return hashlib.md5(str(repo_path).encode()).hexdigest()[:16]


class RepositoryAnalyzerAgent:
    def __init__(self) -> None:
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
        )
        self._indexer = RepositoryIndexer()
        self._retriever = RAGRetriever()

    async def analyze(self, repo_path: Path, ticket_analysis: TicketAnalysis) -> str:
        rid = _repo_id(repo_path)
        indexed = await self._indexer.index_repository(repo_path, rid)

        rag_context = await self._retriever.get_context_for_ticket(
            repo_id=rid,
            title=ticket_analysis.summary,
            description=str(ticket_analysis.type.value),
            files_hint=ticket_analysis.files_probably_related,
        )

        prompt = f"""Ticket analysis:
{ticket_analysis.model_dump_json(indent=2)}

Indexed {indexed} code chunks. Semantically retrieved context:
{rag_context}

Provide a focused technical context report for implementing this ticket."""

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = await self._llm.ainvoke(messages)
        return str(response.content)

    async def cleanup_index(self, repo_path: Path) -> None:
        rid = _repo_id(repo_path)
        await self._retriever.delete_repo(rid)
