import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings


async def chat_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("Chat service is not configured")
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
    )
    try:
        for attempt in range(settings.llm_max_retries):
            try:
                response = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=settings.llm_max_tokens,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty model response")
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ValueError("Model response was not an object")
                return value
            except Exception:
                if attempt == settings.llm_max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
    finally:
        await client.close()
    raise RuntimeError("Chat service failed")
