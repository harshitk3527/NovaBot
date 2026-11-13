from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models import Conversation, Message, MessageRole, User
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag import generate_answer
from app.services.retrieval import embed_query, search_chunks

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if payload.conversation_id is None:
        conversation = Conversation(user_id=user.id, tenant_id=user.tenant_id)
        db.add(conversation)
        await db.flush()
    else:
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == user.id,
                Conversation.tenant_id == user.tenant_id,
            )
        )
        if conversation is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Conversation not found")

    embedding = await embed_query(payload.message)
    chunks = await search_chunks(embedding, user.tenant_id, db=db)
    result = await generate_answer(payload.message, chunks)
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
            content=result.answer,
            citations=[citation.model_dump(mode="json") for citation in result.citations],
        )
    )
    await db.commit()
    return ChatResponse(
        answer=result.answer,
        citations=result.citations,
        conversation_id=conversation.id,
        needs_human=result.needs_human,
    )
