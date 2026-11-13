from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.db import session as db_session
from app.db.models import Chunk, Document, DocumentStatus, User, UserRole
from app.services.rag import FALLBACK_MESSAGE, generate_answer
from app.services.retrieval import RetrievedChunk, search_chunks


def retrieved_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content="Refunds are available within thirty days.",
        title="Refund Policy",
        version="1",
        page=2,
        similarity=0.91,
    )


@pytest.mark.asyncio
async def test_chat_citations_only_reference_retrieved_chunks(client, monkeypatch):
    register = await client.post(
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "correct horse battery"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": register.json()["email"], "password": "correct horse battery"},
    )
    source = retrieved_chunk()

    async def fake_embed(message):
        return [0.0] * 1536

    async def fake_search(embedding, tenant_id, k=None, db=None):
        return [source]

    async def fake_llm(system_prompt, user_prompt):
        return {
            "answer": "Refunds are available within thirty days.",
            "used_sources": ["S1", "S999"],
            "answerable": True,
        }

    monkeypatch.setattr("app.api.chat.embed_query", fake_embed)
    monkeypatch.setattr("app.api.chat.search_chunks", fake_search)
    monkeypatch.setattr("app.services.rag.llm.chat_json", fake_llm)
    response = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"message": "What is the refund period?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["citations"]) == 1
    assert body["citations"][0]["chunk_id"] == str(source.chunk_id)
    assert body["needs_human"] is False


@pytest.mark.asyncio
async def test_invented_only_source_ids_trigger_fallback(client, monkeypatch):
    register = await client.post(
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "correct horse battery"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": register.json()["email"], "password": "correct horse battery"},
    )

    async def fake_embed(message):
        return [0.0] * 1536

    async def fake_search(embedding, tenant_id, k=None, db=None):
        return [retrieved_chunk()]

    async def fake_llm(system_prompt, user_prompt):
        return {"answer": "The answer is 42.", "used_sources": ["S404"], "answerable": True}

    monkeypatch.setattr("app.api.chat.embed_query", fake_embed)
    monkeypatch.setattr("app.api.chat.search_chunks", fake_search)
    monkeypatch.setattr("app.services.rag.llm.chat_json", fake_llm)
    response = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"message": "A question"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == FALLBACK_MESSAGE
    assert response.json()["needs_human"] is True
    assert response.json()["citations"] == []


@pytest.mark.asyncio
async def test_no_retrieved_chunks_use_fallback():
    result = await generate_answer("Unknown question", [])
    assert result.answer == FALLBACK_MESSAGE
    assert result.needs_human is True
    assert result.citations == []


@pytest.mark.asyncio
async def test_search_excludes_expired_documents_and_other_tenants(client):
    async with db_session.AsyncSessionLocal() as db:
        tenant = User(
            email=f"{uuid4()}@example.com",
            password_hash="hash",
            role=UserRole.CUSTOMER,
            tenant_id=uuid4(),
        )
        other_tenant = User(
            email=f"{uuid4()}@example.com",
            password_hash="hash",
            role=UserRole.CUSTOMER,
            tenant_id=uuid4(),
        )
        db.add_all([tenant, other_tenant])
        await db.flush()
        active = Document(
            title="Active",
            version="1",
            status=DocumentStatus.ACTIVE,
            content_hash=uuid4().hex,
            valid_from=datetime.now(timezone.utc),
            uploaded_by=tenant.id,
        )
        expired = Document(
            title="Expired",
            version="1",
            status=DocumentStatus.ACTIVE,
            content_hash=uuid4().hex,
            valid_from=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            uploaded_by=tenant.id,
        )
        other = Document(
            title="Other tenant",
            version="1",
            status=DocumentStatus.ACTIVE,
            content_hash=uuid4().hex,
            valid_from=datetime.now(timezone.utc),
            uploaded_by=other_tenant.id,
        )
        db.add_all([active, expired, other])
        await db.flush()
        db.add_all(
            [
                Chunk(
                    document_id=active.id,
                    content="active",
                    page=1,
                    chunk_index=0,
                    embedding=[1.0] + [0.0] * 1535,
                ),
                Chunk(
                    document_id=expired.id,
                    content="expired",
                    page=1,
                    chunk_index=0,
                    embedding=[1.0] + [0.0] * 1535,
                ),
                Chunk(
                    document_id=other.id,
                    content="other",
                    page=1,
                    chunk_index=0,
                    embedding=[1.0] + [0.0] * 1535,
                ),
            ]
        )
        await db.commit()
        results = await search_chunks([1.0] + [0.0] * 1535, tenant.tenant_id, db=db)

    assert [result.title for result in results] == ["Active"]
