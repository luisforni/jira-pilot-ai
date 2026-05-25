import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from core.config import settings

log = structlog.get_logger()

_VECTOR_SIZE = 1536


class RAGRetriever:
    def __init__(self) -> None:
        self._qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def _embed(self, text: str) -> list[float]:
        response = await self._openai.embeddings.create(
            model="text-embedding-3-small",
            input=[text],
        )
        return response.data[0].embedding

    async def search(
        self,
        query: str,
        repo_id: str,
        top_k: int = 10,
        score_threshold: float = 0.4,
    ) -> list[dict]:
        vector = await self._embed(query)

        results = await self._qdrant.search(
            collection_name=settings.qdrant_collection,
            query_vector=vector,
            query_filter=Filter(
                must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
            ),
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )

        return [
            {
                "file_path": r.payload["file_path"],
                "text": r.payload["text"],
                "score": r.score,
                "chunk_index": r.payload["chunk_index"],
            }
            for r in results
            if r.payload
        ]

    async def get_context_for_ticket(
        self,
        repo_id: str,
        title: str,
        description: str,
        files_hint: list[str] | None = None,
        max_chars: int = 12_000,
    ) -> str:
        query = f"{title}\n{description}"
        chunks = await self.search(query, repo_id, top_k=15)

        if files_hint:
            hinted = [c for c in chunks if any(f in c["file_path"] for f in files_hint)]
            others = [c for c in chunks if c not in hinted]
            chunks = hinted + others

        seen_files: set[str] = set()
        sections: list[str] = []
        total = 0

        for chunk in chunks:
            header = f"### {chunk['file_path']} (score: {chunk['score']:.2f})\n"
            body = chunk["text"]
            block = header + body + "\n"
            if total + len(block) > max_chars:
                break
            sections.append(block)
            seen_files.add(chunk["file_path"])
            total += len(block)

        log.info("rag_context_built", files=len(seen_files), chars=total, repo_id=repo_id)
        return "\n".join(sections)

    async def delete_repo(self, repo_id: str) -> None:
        await self._qdrant.delete(
            collection_name=settings.qdrant_collection,
            points_selector=Filter(
                must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
            ),
        )
        log.info("rag_repo_deleted", repo_id=repo_id)
