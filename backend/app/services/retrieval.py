from dataclasses import dataclass
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Chunk, Document
from app.services.documents import active_documents_filter


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    content: str
    title: str
    version: str
    page: int | None
    similarity: float


async def embed_query(text: str) -> list[float]:
    """Return a reusable query vector; callers can cache this value later."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("Embedding service is not configured")
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
    )
    try:
        for attempt in range(settings.llm_max_retries):
            try:
                response = await client.embeddings.create(
                    model=settings.embedding_model,
                    input=text,
                )
                return response.data[0].embedding
            except Exception:
                if attempt == settings.llm_max_retries - 1:
                    raise
    finally:
        await client.close()
    raise RuntimeError("Embedding service failed")


async def search_chunks(
    embedding: list[float],
    tenant_id: UUID,
    k: int | None = None,
    db: AsyncSession | None = None,
) -> list[RetrievedChunk]:
    if db is None:
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            return await search_chunks(embedding, tenant_id, k=k, db=session)

    settings = get_settings()
    limit = min(k or settings.retrieval_default_k, 50)
    distance = Chunk.embedding.cosine_distance(embedding)
    similarity = (1 - distance).label("similarity")
    statement: Select = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.content,
            Document.title,
            Document.version,
            Chunk.page,
            similarity,
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(
            active_documents_filter(tenant_id),
            Chunk.embedding.is_not(None),
            similarity >= settings.retrieval_similarity_cutoff,
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = (await db.execute(statement)).all()
    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            content=row.content,
            title=row.title,
            version=row.version,
            page=row.page,
            similarity=float(row.similarity),
        )
        for row in rows
    ]
