from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    version: str
    status: DocumentStatus
    content_hash: str
    valid_from: datetime
    expires_at: datetime | None
    uploaded_by: UUID
    superseded_by: UUID | None
    created_at: datetime


class DocumentUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^archive$")
    expires_at: datetime | None = None


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    page: int
    page_size: int
    total: int
