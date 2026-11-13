from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/presidio"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(default="change-me-in-production", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    openai_api_key: str = ""
    app_env: str = "development"
    max_upload_size_bytes: int = 10 * 1024 * 1024
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 100
    ingestion_chunk_tokens: int = 650
    ingestion_chunk_overlap_tokens: int = 100
    staleness_job_interval_seconds: int = 60
    retrieval_similarity_cutoff: float = 0.75
    retrieval_default_k: int = 8
    openai_timeout_seconds: float = 30.0
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 600
    llm_max_retries: int = 3
    rewriter_model: str = "gpt-4o-mini"
    rewriter_max_tokens: int = 120
    max_rewritten_question_length: int = 1000
    memory_window_messages: int = 8
    cache_distance_threshold: float = 0.1
    cache_ttl_seconds: int = 3600
    cache_prompt_version: str = "v1"
    cache_index_name: str = "presidio_semantic_cache"
    max_message_length: int = 4000
    max_output_length: int = 10000
    prompt_canary: str = "PRESIDIO_SYSTEM_CANARY_7F3A"
    cors_allowed_origins: str = "http://localhost:3000"
    max_request_size_bytes: int = 12 * 1024 * 1024
    chat_rate_limit_per_minute: int = 20
    login_rate_limit_per_minute: int = 5
    rate_limit_window_seconds: int = 60
    daily_token_budget: int = 100000
    login_failure_limit: int = 5
    login_lockout_seconds: int = 900
    pii_redaction_enabled: bool = True
    moderation_enabled: bool = True
    scope_classifier_enabled: bool = True
    scope_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
