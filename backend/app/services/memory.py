from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Conversation, Message, User


async def get_or_create_conversation(
    db: AsyncSession,
    user: User,
    conversation_id: UUID | None,
) -> Conversation:
    if conversation_id is None:
        conversation = Conversation(user_id=user.id, tenant_id=user.tenant_id)
        db.add(conversation)
        await db.flush()
        return conversation
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.tenant_id == user.tenant_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def load_history(
    db: AsyncSession,
    conversation: Conversation,
    limit: int | None = None,
) -> list[Message]:
    window = limit or get_settings().memory_window_messages
    messages = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(window)
        )
    ).all()
    return list(reversed(messages))


async def list_conversations(db: AsyncSession, user: User) -> list[Conversation]:
    return list(
        (
            await db.scalars(
                select(Conversation)
                .where(
                    Conversation.user_id == user.id,
                    Conversation.tenant_id == user.tenant_id,
                )
                .order_by(Conversation.created_at.desc())
            )
        ).all()
    )


async def list_messages(
    db: AsyncSession, conversation_id: UUID, user: User
) -> list[Message]:
    conversation = await _owned_conversation(db, conversation_id, user)
    return list(
        (
            await db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).all()
    )


async def delete_conversation(
    db: AsyncSession, conversation_id: UUID, user: User
) -> None:
    conversation = await _owned_conversation(db, conversation_id, user)
    await db.execute(delete(Message).where(Message.conversation_id == conversation.id))
    await db.delete(conversation)
    await db.commit()


async def _owned_conversation(
    db: AsyncSession, conversation_id: UUID, user: User
) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.tenant_id == user.tenant_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
