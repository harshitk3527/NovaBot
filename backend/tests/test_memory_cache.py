from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db import session as db_session
from app.db.models import Conversation, Document, DocumentStatus, Message, MessageRole, User, UserRole
from app.schemas.chat import CitationResponse
from app.services.cache import get_cached_answer
from app.services.memory import load_history
from app.services.retrieval import RetrievedChunk


async def customer_token(client) -> tuple[str, str]:
    email = f"{uuid4()}@example.com"
    await client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "correct horse battery"},
    )
    return email, login.json()["access_token"]


def source() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content="Support answer source.",
        title="Support",
        version="1",
        page=1,
        similarity=0.95,
    )


@pytest.mark.asyncio
async def test_history_summarizes_old_messages_and_keeps_recent_five(monkeypatch):
    messages = [
        Message(role=MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT, content=f"message {index}")
        for index in range(16)
    ]

    class Result:
        def all(self):
            return list(reversed(messages))

    class FakeDB:
        async def scalars(self, query):
            return Result()

    async def fake_summary(**kwargs):
        return "summary of ten messages"

    monkeypatch.setattr("app.services.memory.chat_text", fake_summary)
    history = await load_history(FakeDB(), Conversation(), limit=15)

    assert len(history) == 6
    assert history[0].role == MessageRole.SYSTEM
    assert history[0].content == "Earlier conversation summary: summary of ten messages"
    assert [message.content for message in history[1:]] == [
        "message 11",
        "message 12",
        "message 13",
        "message 14",
        "message 15",
    ]


@pytest.mark.asyncio
async def test_paraphrased_question_hits_cache_without_llm(
    client, monkeypatch
):
    _, token = await customer_token(client)
    calls = {"llm": 0, "lookup": 0}
    cached = None
    retrieved = source()
    citation = CitationResponse(
        document_id=retrieved.document_id,
        title=retrieved.title,
        version=retrieved.version,
        page=retrieved.page,
        chunk_id=retrieved.chunk_id,
        snippet=retrieved.content,
    )

    async def fake_embed(question):
        return [0.0] * 1536

    async def fake_search(embedding, tenant_id, k=None, db=None):
        return [retrieved]

    async def fake_generate(question, chunks):
        calls["llm"] += 1
        from app.services.rag import RAGResult

        return RAGResult("Cached answer", [citation], False)

    async def fake_lookup(question, embedding, tenant_id, kb_version, db):
        calls["lookup"] += 1
        return cached

    async def fake_store(question, embedding, tenant_id, kb_version, answer, citations):
        nonlocal cached
        cached = (answer, citations)

    monkeypatch.setattr("app.api.chat.embed_query", fake_embed)
    monkeypatch.setattr("app.api.chat.search_chunks", fake_search)
    monkeypatch.setattr("app.api.chat.generate_answer", fake_generate)
    monkeypatch.setattr("app.api.chat.cache.get_cached_answer", fake_lookup)
    monkeypatch.setattr("app.api.chat.cache.store_cached_answer", fake_store)
    first = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "What is the refund policy?"},
    )
    second = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Can you explain the refund policy?"},
    )
    assert first.status_code == second.status_code == 200
    assert calls["lookup"] == 2
    assert calls["llm"] == 1
    assert second.json()["cached"] is True


@pytest.mark.asyncio
async def test_follow_up_is_rewritten_using_history(client, monkeypatch):
    _, token = await customer_token(client)
    rewrite_inputs = []

    async def fake_rewrite(question, history):
        rewrite_inputs.append((question, [message.content for message in history]))
        return "What is the second refund option?"

    embedded_questions = []

    async def fake_embed(question):
        embedded_questions.append(question)
        return [0.0] * 1536

    async def fake_lookup(*args):
        return None

    async def fake_search(*args, **kwargs):
        return []

    monkeypatch.setattr("app.api.chat.rewrite_question", fake_rewrite)
    monkeypatch.setattr("app.api.chat.embed_query", fake_embed)
    monkeypatch.setattr("app.api.chat.cache.get_cached_answer", fake_lookup)
    monkeypatch.setattr("app.api.chat.search_chunks", fake_search)
    first = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "What are the refund options?"},
    )
    second = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": "what about the second one?",
            "conversation_id": first.json()["conversation_id"],
        },
    )
    assert first.status_code == second.status_code == 200
    assert rewrite_inputs[0][0] == "what about the second one?"
    assert rewrite_inputs[0][1]
    assert embedded_questions == [
        "What are the refund options?",
        "What is the second refund option?",
    ]


@pytest.mark.asyncio
async def test_kb_version_change_misses_existing_cache(client, monkeypatch):
    _, token = await customer_token(client)
    versions = iter((1, 2))
    stored = {}
    llm_calls = 0

    async def fake_version(tenant_id):
        return next(versions)

    async def fake_lookup(question, embedding, tenant_id, kb_version, db):
        return stored.get(kb_version)

    async def fake_store(question, embedding, tenant_id, kb_version, answer, citations):
        stored[kb_version] = (answer, citations)

    async def fake_embed(question):
        return [0.0] * 1536

    async def fake_search(*args, **kwargs):
        return []

    async def fake_generate(*args):
        nonlocal llm_calls
        llm_calls += 1
        from app.services.rag import RAGResult

        return RAGResult("answer", [], False)

    monkeypatch.setattr("app.api.chat.cache.current_kb_version", fake_version)
    monkeypatch.setattr("app.api.chat.cache.get_cached_answer", fake_lookup)
    monkeypatch.setattr("app.api.chat.cache.store_cached_answer", fake_store)
    monkeypatch.setattr("app.api.chat.embed_query", fake_embed)
    monkeypatch.setattr("app.api.chat.search_chunks", fake_search)
    monkeypatch.setattr("app.api.chat.generate_answer", fake_generate)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/chat", headers=headers, json={"message": "Same question"})
    await client.post("/chat", headers=headers, json={"message": "Same question"})
    assert llm_calls == 2


@pytest.mark.asyncio
async def test_other_users_conversation_returns_404(client):
    _, first_token = await customer_token(client)
    _, second_token = await customer_token(client)
    first = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {first_token}"},
        json={"message": "Hello"},
    )
    response = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {second_token}"},
        json={
            "message": "Can I see it?",
            "conversation_id": first.json()["conversation_id"],
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_redis_outage_degrades_to_cache_miss(client, monkeypatch):
    _, token = await customer_token(client)

    class BrokenCache:
        async def acheck(self, **kwargs):
            raise ConnectionError("redis unavailable")

        async def astore(self, **kwargs):
            raise ConnectionError("redis unavailable")

    async def broken_version(tenant_id):
        raise ConnectionError("redis unavailable")

    async def fake_embed(question):
        return [0.0] * 1536

    async def fake_search(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.cache._cache", lambda: BrokenCache())
    monkeypatch.setattr("app.services.cache.get_kb_version", broken_version)
    monkeypatch.setattr("app.api.chat.embed_query", fake_embed)
    monkeypatch.setattr("app.api.chat.search_chunks", fake_search)
    response = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Question during outage"},
    )
    assert response.status_code == 200
    assert response.json()["needs_human"] is True


@pytest.mark.asyncio
async def test_expired_cached_document_is_evicted(client, monkeypatch):
    async with db_session.AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid4()}@example.com",
            password_hash="hash",
            role=UserRole.CUSTOMER,
            tenant_id=uuid4(),
        )
        db.add(user)
        await db.flush()
        document = Document(
            title="Expired",
            version="1",
            status=DocumentStatus.ACTIVE,
            content_hash=uuid4().hex,
            valid_from=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            uploaded_by=user.id,
        )
        db.add(document)
        await db.commit()
        citation = CitationResponse(
            document_id=document.id,
            title=document.title,
            version=document.version,
            page=1,
            chunk_id=uuid4(),
            snippet="expired",
        )

        class FakeCache:
            async def acheck(self, **kwargs):
                return [
                    {
                        "id": "novabot_semantic_cache:expired",
                        "response": "stale answer",
                        "metadata": {"citations": [citation.model_dump(mode="json")]},
                    }
                ]

            async def adrop(self, **kwargs):
                self.dropped = True

        fake_cache = FakeCache()
        monkeypatch.setattr("app.services.cache._cache", lambda: fake_cache)
        result = await get_cached_answer(
            "question", [0.0] * 1536, user.tenant_id, 1, db
        )
    assert result is None
    assert fake_cache.dropped is True


def test_cache_filter_is_tenant_specific():
    from app.services.cache import _filters

    first = uuid4()
    second = uuid4()
    assert str(_filters(first, 3)) != str(_filters(second, 3))
