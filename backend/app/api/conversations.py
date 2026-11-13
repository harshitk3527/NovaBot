from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.conversations import ConversationResponse, MessageResponse
from app.services.memory import delete_conversation, list_conversations, list_messages

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
async def get_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await list_conversations(db, user)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await list_messages(db, conversation_id, user)


@router.delete("/{conversation_id}", status_code=204)
async def remove_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_conversation(db, conversation_id, user)
