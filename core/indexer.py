import hashlib
import uuid
from pathlib import Path

import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from core.config import settings

log = structlog.get_logger()

VECTOR_SIZE = 1536  # text-embedding-3-small
CHUNK_SIZE = 1500   # chars per chunk
CHUNK_OVERLAP = 200

_EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
_TEXT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rb", ".rs",
    ".md", ".yaml", ".yml", ".toml", ".json", ".sh", ".sql",
}
_MAX_FILE_SIZE = 100_000


def _chunk_text(text: str, file_path: str) -> list[dict]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end]
        chunks.append({
            "text": chunk,
            "file_path": file_path,
            "chunk_index": len(chunks),
            "start_char": start,
        })
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _stable_id(repo_id: str, file_path: str, chunk_index: int) -> str:
    key = f"{repo_id}:{file_path}:{chunk_index}"
    return str(uuid.UUID(hashlib.md5(key.encode()).hexdigest()))


class RepositoryIndexer:
    def __init__(self) -> None:
        self._qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def ensure_collection(self) -> None:
        collections = await self._qdrant.get_collections()
        names = [c.name for c in collections.collections]
        if settings.qdrant_collection not in names:
            await self._qdrant.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            log.info("qdrant_collection_created", name=settings.qdrant_collection)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._openai.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def index_repository(self, repo_path: Path, repo_id: str) -> int:
        await self.ensure_collection()

        all_chunks: list[dict] = []
        for path in sorted(repo_path.rglob("*")):
            if any(excluded in path.parts for excluded in _EXCLUDED_DIRS):
                continue
            if not path.is_file() or path.suffix not in _TEXT_EXTENSIONS:
                continue
            if path.stat().st_size > _MAX_FILE_SIZE:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(path.relative_to(repo_path))
            all_chunks.extend(_chunk_text(content, rel))

        if not all_chunks:
            return 0

        batch_size = 50
        total_indexed = 0

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            texts = [c["text"] for c in batch]
            vectors = await self._embed(texts)

            points = [
                PointStruct(
                    id=_stable_id(repo_id, c["file_path"], c["chunk_index"]),
                    vector=vec,
                    payload={
                        "repo_id": repo_id,
                        "file_path": c["file_path"],
                        "chunk_index": c["chunk_index"],
                        "start_char": c["start_char"],
                        "text": c["text"],
                    },
                )
                for c, vec in zip(batch, vectors)
            ]

            await self._qdrant.upsert(
                collection_name=settings.qdrant_collection,
                points=points,
            )
            total_indexed += len(points)
            log.info("indexed_batch", repo_id=repo_id, total=total_indexed)

        return total_indexed
