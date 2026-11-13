import json
from functools import lru_cache
from typing import Any
from uuid import UUID

from redisvl.extensions.cache.llm import SemanticCache
from redisvl.query.filter import Tag
from redisvl.utils.vectorize.base import BaseVectorizer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Document, User
from app.schemas.chat import CitationResponse
from app.services.documents import active_documents_filter
from app.services.redis_version import get_kb_version


@lru_cache
def _cache() -> SemanticCache:
    settings = get_settings()
    vectorizer = BaseVectorizer(model=settings.embedding_model, dims=1536)
    return SemanticCache(
        name=settings.cache_index_name,
        distance_threshold=settings.cache_distance_threshold,
        ttl=settings.cache_ttl_seconds,
        vectorizer=vectorizer,
        filterable_fields=[
            {"name": "tenant_id", "type": "tag"},
            {"name": "kb_version", "type": "tag"},
            {"name": "prompt_version", "type": "tag"},
        ],
        redis_url=settings.redis_url,
    )


async def current_kb_version(tenant_id: UUID) -> int:
    try:
        return await get_kb_version(tenant_id)
    except Exception:
        return 0


def _filters(tenant_id: UUID, kb_version: int) -> Any:
    settings = get_settings()
    return (
        (Tag("tenant_id") == str(tenant_id))
        & (Tag("kb_version") == str(kb_version))
        & (Tag("prompt_version") == settings.cache_prompt_version)
    )


def _metadata(hit: dict[str, Any]) -> dict[str, Any]:
    value = hit.get("metadata") or {}
    if isinstance(value, str):
        return json.loads(value)
    return value


async def get_cached_answer(
    question: str,
    embedding: list[float],
    tenant_id: UUID,
    kb_version: int,
    db: AsyncSession,
) -> tuple[str, list[CitationResponse]] | None:
    try:
        hits = await _cache().acheck(
            vector=embedding,
            num_results=1,
            filter_expression=_filters(tenant_id, kb_version),
        )
        if not hits:
            return None
        hit = hits[0]
        metadata = _metadata(hit)
        citations = [CitationResponse.model_validate(item) for item in metadata.get("citations", [])]
        document_ids = {citation.document_id for citation in citations}
        if document_ids:
            active_count = await db.scalar(
                select(func.count(Document.id))
                .join(User, Document.uploaded_by == User.id)
                .where(
                    Document.id.in_(document_ids),
                    active_documents_filter(tenant_id),
                )
            )
            if active_count != len(document_ids):
                await _evict(hit)
                return None
        return str(hit["response"]), citations
    except Exception:
        return None


async def store_cached_answer(
    question: str,
    embedding: list[float],
    tenant_id: UUID,
    kb_version: int,
    answer: str,
    citations: list[CitationResponse],
) -> None:
    try:
        await _cache().astore(
            prompt=question,
            response=answer,
            vector=embedding,
            filters={
                "tenant_id": str(tenant_id),
                "kb_version": str(kb_version),
                "prompt_version": get_settings().cache_prompt_version,
            },
            metadata={
                "citations": [citation.model_dump(mode="json") for citation in citations],
                "source_document_ids": [str(citation.document_id) for citation in citations],
            },
        )
    except Exception:
        return


async def _evict(hit: dict[str, Any]) -> None:
    try:
        key = hit.get("id")
        if key:
            await _cache().adrop(keys=[key])
        elif hit.get("entry_id"):
            await _cache().adrop(ids=[hit["entry_id"]])
    except Exception:
        return


def is_cacheable(question: str, flagged: bool, needs_human: bool) -> bool:
    if flagged or needs_human:
        return False
    normalized = question.lower()
    personal_markers = (
        "my order",
        "my account",
        "my payment",
        "my invoice",
        "my subscription",
        "my case",
        "my ticket",
    )
    return not any(marker in normalized for marker in personal_markers)
