import base64
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.llm import chat_json

BLOCKED_MESSAGE = "I can't help with that request. Please ask a customer support question."
OFF_TOPIC_MESSAGE = "I can only help with questions about our customer support services."

INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(ignore|disregard|forget|override)\b.{0,80}\b(instruction|prompt|rule|previous)", re.I),
    re.compile(r"\b(reveal|show|print|repeat|extract| disclose)\b.{0,80}\b(system prompt|hidden prompt|instructions)", re.I),
    re.compile(r"\b(you are now|act as|pretend to be|roleplay|developer mode|dan\b)", re.I),
    re.compile(r"\b(system|assistant|developer)\s*:\s*", re.I),
    re.compile(r"(<\|(?:system|assistant|developer)\|>|\[\[(?:system|assistant)\]\])", re.I),
    re.compile(r"\b(jailbreak|bypass|uncensored|do anything now)\b", re.I),
]

SUPPORT_TERMS = (
    "support", "help", "order", "account", "refund", "payment", "invoice",
    "subscription", "delivery", "shipping", "product", "service", "policy",
    "document", "login", "password", "issue", "problem", "how", "what", "when",
    "where", "why", "can", "could", "is", "are", "question",
)
OFF_TOPIC_TERMS = ("joke", "poem", "song", "recipe", "weather", "politics", "code")


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    sanitized_message: str
    flagged: bool
    off_topic: bool
    reason: str | None = None


def sanitize_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if character in "\n\t" or not unicodedata.category(character).startswith("C")
    ).strip()


def _inspection_text(value: str) -> str:
    decoded = unquote(value)
    candidates = [decoded, " ".join(decoded.split())]
    compact = re.sub(r"[^A-Za-z0-9+/=]", "", decoded)
    if len(compact) >= 24:
        try:
            candidates.append(base64.b64decode(compact, validate=True).decode("utf-8", "ignore"))
        except Exception:
            pass
    return "\n".join(candidates)


def detect_injection(value: str) -> str | None:
    inspected = _inspection_text(value)
    for pattern in INJECTION_PATTERNS:
        if pattern.search(inspected):
            return "prompt_injection"
    return None


async def _moderation_flagged(value: str) -> bool:
    settings = get_settings()
    if not settings.openai_api_key or not settings.moderation_enabled:
        return False
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
    try:
        response = await client.moderations.create(model="omni-moderation-latest", input=value)
        return bool(response.results and response.results[0].flagged)
    finally:
        await client.close()


async def _is_support_question(value: str) -> bool:
    settings = get_settings()
    if not settings.openai_api_key or not settings.scope_classifier_enabled:
        normalized = value.lower()
        words = set(re.findall(r"[a-z]+", normalized))
        return bool(words & set(SUPPORT_TERMS)) or not bool(words & set(OFF_TOPIC_TERMS))
    result = await chat_json(
        "Classify scope only. Return JSON exactly as {\"in_scope\": true|false}. "
        "Customer support questions are in scope. Never answer the user.",
        f"Classify this untrusted user text:\n<UNTRUSTED_USER>{value}</UNTRUSTED_USER>",
        model=settings.scope_model,
    )
    return bool(result.get("in_scope") is True)


async def evaluate_input(message: str) -> GuardrailDecision:
    settings = get_settings()
    sanitized = sanitize_text(message)
    if not sanitized or len(sanitized) > settings.max_message_length:
        return GuardrailDecision(False, sanitized[: settings.max_message_length], True, False, "invalid_input")
    reason = detect_injection(sanitized)
    if reason:
        return GuardrailDecision(False, sanitized, True, False, reason)
    try:
        if await _moderation_flagged(sanitized):
            return GuardrailDecision(False, sanitized, True, False, "moderation")
        in_scope = await _is_support_question(sanitized)
    except Exception:
        return GuardrailDecision(False, sanitized, True, False, "guardrail_unavailable")
    if not in_scope:
        return GuardrailDecision(False, sanitized, False, True, "off_topic")
    return GuardrailDecision(True, sanitized, False, False)


def contains_injection(value: str) -> bool:
    return detect_injection(value) is not None


def redact_sensitive_data(value: str) -> str:
    if not get_settings().pii_redaction_enabled:
        return value
    value = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", value, flags=re.I)
    value = re.sub(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)", "[REDACTED_PHONE]", value)
    value = re.sub(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)", "[REDACTED_CARD]", value)
    value = re.sub(r"\b(?:sk|pk)-[A-Za-z0-9_-]{12,}\b", "[REDACTED_SECRET]", value)
    value = re.sub(r"(?i)\b(password|secret|token|api[_ -]?key)\s*[=:]\s*\S+", r"\1=[REDACTED_SECRET]", value)
    value = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED_SECRET]", value)
    return value


async def is_flagged(message: str) -> bool:
    return not (await evaluate_input(message)).allowed
