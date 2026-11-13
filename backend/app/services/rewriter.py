from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.db.models import Message
from app.services.memory import HistoryMessage
from app.services.llm import chat_text


class StandaloneQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)


async def rewrite_question(
    question: str, history: Sequence[Message | HistoryMessage]
) -> str:
    if not history:
        return question.strip()
    settings = get_settings()
    history_text = "\n".join(f"{message.role.value}: {message.content}" for message in history)
    prompt = (
        "Rewrite the latest customer message as one standalone question. "
        "Resolve references using the conversation history. Output only the question, "
        "with no quotes, explanation, or answer.\n\n"
        f"Conversation history:\n{history_text}\n\nLatest message:\n{question}"
    )
    rewritten = await chat_text(
        system_prompt=(
            "You rewrite customer support follow-ups into standalone questions. "
            "Do not answer the question."
        ),
        user_prompt=prompt,
        model=settings.rewriter_model,
        max_tokens=settings.rewriter_max_tokens,
    )
    validated = StandaloneQuestion.model_validate({"question": rewritten.strip()})
    if len(validated.question) > settings.max_rewritten_question_length:
        raise ValueError("Rewritten question is too long")
    return validated.question
