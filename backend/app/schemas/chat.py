from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    conversation_id: UUID | None = None


class CitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    title: str
    version: str
    page: int | None
    chunk_id: UUID
    snippet: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[CitationResponse]
    conversation_id: UUID
    needs_human: bool
    cached: bool


class LLMAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=10000)
    used_sources: list[str] = Field(default_factory=list, max_length=32)
    answerable: bool
