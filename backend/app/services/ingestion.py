import asyncio
import hashlib
import io
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import tiktoken
from docx import Document as DocxDocument
from openai import AsyncOpenAI
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AuditLog, Chunk, Document, DocumentStatus, User
from app.db.session import AsyncSessionLocal
from app.services.redis_version import increment_kb_version
from app.services.guardrails import contains_injection

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def validate_upload(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type")
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("Invalid file contents")
    if extension == ".docx" and not content.startswith(b"PK"):
        raise ValueError("Invalid file contents")
    if extension in {".txt", ".md"}:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Invalid file contents") from None
    return extension


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pages(extension: str, content: bytes) -> list[tuple[int, str]]:
    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        return [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
    if extension == ".docx":
        document = DocxDocument(io.BytesIO(content))
        return [(1, "\n".join(paragraph.text for paragraph in document.paragraphs))]
    return [(1, content.decode("utf-8"))]


def chunk_pages(
    pages: Sequence[tuple[int, str]],
    chunk_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[tuple[int, int, str]]:
    settings = get_settings()
    size = chunk_tokens or settings.ingestion_chunk_tokens
    overlap = overlap_tokens if overlap_tokens is not None else settings.ingestion_chunk_overlap_tokens
    if overlap >= size:
        raise ValueError("Chunk overlap must be smaller than chunk size")
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks: list[tuple[int, int, str]] = []
    chunk_index = 0
    for page, text in pages:
        tokens = encoding.encode(text)
        start = 0
        while start < len(tokens):
            end = min(start + size, len(tokens))
            chunk_text = encoding.decode(tokens[start:end]).strip()
            if chunk_text:
                chunks.append((page, chunk_index, chunk_text))
                chunk_index += 1
            if end == len(tokens):
                break
            start = end - overlap
    return chunks


async def embed_chunks(texts: Sequence[str]) -> list[list[float]]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("Embedding service is not configured")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    embeddings: list[list[float]] = []
    try:
        for start in range(0, len(texts), settings.embedding_batch_size):
            batch = list(texts[start : start + settings.embedding_batch_size])
            for attempt in range(3):
                try:
                    response = await client.embeddings.create(
                        model=settings.embedding_model,
                        input=batch,
                    )
                    embeddings.extend(item.embedding for item in response.data)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
    finally:
        await client.close()
    return embeddings


async def process_document(
    document_id: UUID,
    tenant_id: UUID,
    filename: str,
    content: bytes,
) -> None:
    try:
        extension = validate_upload(filename, content)
        pages = extract_pages(extension, content)
        chunks = chunk_pages(pages)
        needs_review = any(contains_injection(item[2]) for item in chunks)
        embeddings = await embed_chunks([item[2] for item in chunks]) if chunks else []
        superseded_tenant = False
        async with AsyncSessionLocal() as db:
            async with db.begin():
                document = await db.get(Document, document_id, with_for_update=True)
                if document is None:
                    return
                previous = await db.scalar(
                    select(Document)
                    .join(User, Document.uploaded_by == User.id)
                    .where(
                        Document.title == document.title,
                        User.tenant_id == tenant_id,
                        Document.status == DocumentStatus.ACTIVE,
                    )
                    .where(Document.id != document.id)
                    .with_for_update()
                )
                if previous is not None:
                    previous.status = DocumentStatus.SUPERSEDED
                    previous.superseded_by = document.id
                    db.add(
                        AuditLog(
                            user_id=document.uploaded_by,
                            action="document.supersede",
                            details={"document_id": str(previous.id), "replacement_id": str(document.id)},
                        )
                    )
                    await db.flush()
                    superseded_tenant = True
                document.status = DocumentStatus.ACTIVE
                document.needs_review = needs_review
                for (page, index, text), embedding in zip(chunks, embeddings):
                    db.add(
                        Chunk(
                            document_id=document.id,
                            content=text,
                            page=page,
                            chunk_index=index,
                            embedding=embedding,
                        )
                    )
                db.add(
                    AuditLog(
                        user_id=document.uploaded_by,
                        action="document.needs_review" if needs_review else "document.ready",
                        details={"document_id": str(document.id), "needs_review": needs_review},
                    )
                )
        if superseded_tenant:
            await increment_kb_version(tenant_id)
    except Exception:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                document = await db.get(Document, document_id, with_for_update=True)
                if document is not None:
                    document.status = DocumentStatus.FAILED
                    db.add(
                        AuditLog(
                            user_id=document.uploaded_by,
                            action="document.failed",
                            details={"document_id": str(document.id)},
                        )
                    )
