from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.services.rag import generate_answer
from app.services.retrieval import RetrievedChunk


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content="Refunds are available within 30 days.",
        title="Refund policy",
        version="1",
        page=1,
        similarity=0.9,
    )


@pytest.mark.asyncio
async def test_canary_leakage_returns_fallback(monkeypatch):
    async def leaked_answer(*args, **kwargs):
        return {
            "answer": f"Leaked {get_settings().prompt_canary}",
            "used_sources": ["S1"],
            "answerable": True,
        }

    monkeypatch.setattr("app.services.rag.llm.chat_json", leaked_answer)
    result = await generate_answer("What is the refund policy?", [_chunk()])
    assert result.needs_human is True
    assert result.citations == []


@pytest.mark.asyncio
async def test_off_topic_guardrail_does_not_call_main_llm(monkeypatch):
    from app.services.guardrails import evaluate_input

    settings = get_settings()
    old_moderation = settings.moderation_enabled
    old_scope = settings.scope_classifier_enabled
    settings.moderation_enabled = False
    settings.scope_classifier_enabled = False
    try:
        called = False

        async def main_llm(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("main LLM must not be called")

        monkeypatch.setattr("app.api.chat.generate_answer", main_llm)
        decision = await evaluate_input("Tell me a joke")
        assert decision.off_topic is True
        assert called is False
    finally:
        settings.moderation_enabled = old_moderation
        settings.scope_classifier_enabled = old_scope


@pytest.mark.asyncio
async def test_chat_rate_limit_returns_429(client, monkeypatch):
    email = f"{uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    login = await client.post("/auth/login", json={"email": email, "password": "correct horse battery"})

    async def denied(*args, **kwargs):
        return False

    monkeypatch.setattr("app.api.chat.allow_request", denied)
    response = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"message": "What is the refund policy?"},
    )
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_daily_token_budget_returns_429(client, monkeypatch):
    email = f"{uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    login = await client.post("/auth/login", json={"email": email, "password": "correct horse battery"})

    async def allowed(*args, **kwargs):
        return True

    async def exhausted(*args, **kwargs):
        return False

    monkeypatch.setattr("app.api.chat.allow_request", allowed)
    monkeypatch.setattr("app.api.chat.reserve_token_budget", exhausted)
    response = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"message": "What is the refund policy?"},
    )
    assert response.status_code == 429
