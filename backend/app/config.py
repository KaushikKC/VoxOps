"""Application configuration.

All settings are loaded from environment variables (or a local ``.env`` file)
and have offline-safe defaults so the service runs with zero external
credentials. See ``.env.example`` for documentation of every value.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Database ---
    database_url: str = "sqlite:///./data/observability.db"

    # --- ElevenLabs webhook ---
    elevenlabs_webhook_secret: str = ""
    elevenlabs_verify_signature: bool = True
    elevenlabs_api_key: str = ""

    # --- Sentiment / task-completion judge ---
    anthropic_api_key: str = ""
    sentiment_model: str = "claude-haiku-4-5-20251001"

    # --- Semantic transcript search (Chroma) ---
    chroma_persist_dir: str = "./data/chroma"
    embeddings_backend: str = "hash"

    # --- SLO / alerting thresholds ---
    slo_llm_ttfb_p95_ms: float = 1500.0
    slo_success_rate_min: float = 0.85
    slo_interruption_rate_max: float = 0.25

    # --- Cost model (USD) ---
    cost_per_call_minute_usd: float = 0.08

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def use_claude_sentiment(self) -> bool:
        """Claude is used for analysis only when an API key is present."""
        return bool(self.anthropic_api_key.strip())

    # Validation of the webhook secret is enforced at request time rather than
    # at startup so the app can boot for local development and the simulator.
    webhook_max_age_seconds: int = Field(
        default=1800,
        description="Reject webhooks whose signed timestamp is older than this.",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance (one per process)."""
    return Settings()
