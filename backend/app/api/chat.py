from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models import AuditLog, Message, MessageRole, User
from app.core.config import get_settings
from app.services.abuse import allow_request, reserve_token_budget
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import cache
from app.services.guardrails import BLOCKED_MESSAGE, OFF_TOPIC_MESSAGE, evaluate_input
from app.services.memory import get_or_create_conversation, load_history
from app.services.rag import generate_answer
from app.services.rewriter import rewrite_question
from app.services.retrieval import embed_query, search_chunks

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    settings = get_settings()
    ip = request.client.host if request.client else "unknown"
    if not await allow_request("chat-ip", ip, settings.chat_rate_limit_per_minute):
        db.add(AuditLog(user_id=user.id, action="rate_limit.chat", ip=ip, details=None))
        await db.commit()
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if not await allow_request("chat-user", str(user.id), settings.chat_rate_limit_per_minute):
        db.add(AuditLog(user_id=user.id, action="rate_limit.chat", ip=ip, details=None))
        await db.commit()
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    decision = await evaluate_input(payload.message)
    conversation = await get_or_create_conversation(db, user, payload.conversation_id)
    if not decision.allowed:
        answer = OFF_TOPIC_MESSAGE if decision.off_topic else BLOCKED_MESSAGE
        db.add(AuditLog(user_id=user.id, action="guardrail.blocked", ip=ip, details={"reason": decision.reason}))
        db.add(Message(conversation_id=conversation.id, role=MessageRole.USER, content=decision.sanitized_message))
        db.add(Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=answer, citations=[]))
        await db.commit()
        return ChatResponse(
            answer=answer, citations=[], conversation_id=conversation.id,
            needs_human=True, cached=False,
        )
    if not await reserve_token_budget(
        user.id, min(settings.llm_max_tokens, settings.max_output_length // 4) + len(decision.sanitized_message) // 4
    ):
        db.add(AuditLog(user_id=user.id, action="token_budget.exceeded", ip=ip, details=None))
        await db.commit()
        raise HTTPException(status_code=429, detail="Daily token budget exceeded")
    history = await load_history(db, conversation)
    standalone_question = (
        await rewrite_question(decision.sanitized_message, history) if history else decision.sanitized_message
    )
    embedding = await embed_query(standalone_question)
    kb_version = await cache.current_kb_version(user.tenant_id)
    cached_result = None
    cached_result = await cache.get_cached_answer(
        standalone_question, embedding, user.tenant_id, kb_version, db
    )
    if cached_result is not None:
        answer, citations = cached_result
        needs_human = False
        cached = True
    else:
        chunks = await search_chunks(embedding, user.tenant_id, db=db)
        result = await generate_answer(standalone_question, chunks)
        answer, citations, needs_human = result.answer, result.citations, result.needs_human
        cached = False
        if cache.is_cacheable(standalone_question, False, needs_human):
            await cache.store_cached_answer(
                standalone_question,
                embedding,
                user.tenant_id,
                kb_version,
                answer,
                citations,
            )
    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=decision.sanitized_message,
            citations=None,
        )
    )
    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            citations=[citation.model_dump(mode="json") for citation in citations],
        )
    )
    await db.commit()
    return ChatResponse(
        answer=answer,
        citations=citations,
        conversation_id=conversation.id,
        needs_human=needs_human,
        cached=cached,
    )
