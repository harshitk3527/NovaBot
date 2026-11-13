from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models import Message, MessageRole, User
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import cache
from app.services.guardrails import is_flagged
from app.services.memory import get_or_create_conversation, load_history
from app.services.rag import generate_answer
from app.services.rewriter import rewrite_question
from app.services.retrieval import embed_query, search_chunks

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    flagged = await is_flagged(payload.message)
    conversation = await get_or_create_conversation(db, user, payload.conversation_id)
    history = await load_history(db, conversation)
    standalone_question = (
        await rewrite_question(payload.message, history) if history else payload.message
    )
    embedding = await embed_query(standalone_question)
    kb_version = await cache.current_kb_version(user.tenant_id)
    cached_result = None
    if not flagged:
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
        if cache.is_cacheable(standalone_question, flagged, needs_human):
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
            content=payload.message,
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
