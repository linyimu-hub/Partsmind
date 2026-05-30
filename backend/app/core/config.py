"""
app/core/config.py
─────────────────
Single source of truth for all application settings.
Loaded once at startup from environment variables / .env file.

Usage:
    from app.core.config import settings
    print(settings.openai_api_key)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore unknown env vars silently
    )

    # ─── App ──────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    allowed_origins: list[str] = ["http://localhost:3000"]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ─── OpenAI ────────────────────────────────────────────────
    openai_api_key: str = Field(..., description="OpenAI API key — required")
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"
    openai_vision_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_max_tokens: int = 2048
    openai_temperature: float = 0.1   # low temp = deterministic for Q&A

    # ─── LangSmith ─────────────────────────────────────────────
    langchain_api_key: str | None = None
    langchain_tracing_v2: bool = False
    langchain_project: str = "partsmind-dev"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # ─── Database ──────────────────────────────────────────────
    database_url: str = Field(..., description="Async PostgreSQL URL — required")
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False   # set True to log SQL queries in dev

    # ─── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600        # 1 hour default cache

    # ─── Auth ──────────────────────────────────────────────────
    secret_key: str = Field(..., description="JWT signing secret — required")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ─── Storage ───────────────────────────────────────────────
    storage_backend: Literal["local", "s3"] = "local"
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 50
    allowed_image_types: list[str] = ["image/jpeg", "image/png", "image/webp"]
    allowed_doc_types: list[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    # AWS S3 (only needed when storage_backend = "s3")
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_s3_bucket: str | None = None
    aws_region: str = "ap-east-1"

    # ─── Agent ─────────────────────────────────────────────────
    agent_max_iterations: int = 8       # guard against infinite loops
    agent_timeout_seconds: int = 60
    rag_top_k: int = 5                  # top-K chunks to retrieve
    rag_similarity_threshold: float = 0.5  # min cosine sim to include

    # ─── Sentry ────────────────────────────────────────────────
    sentry_dsn: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Returns cached Settings instance.
    @lru_cache ensures .env is read only once per process.
    Use in FastAPI with Depends(get_settings) or import directly.
    """
    return Settings()


# Module-level singleton — import this everywhere
settings = get_settings()
