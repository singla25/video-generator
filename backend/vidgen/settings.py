"""Application settings, read from ``VIDGEN_*`` environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configurable values. Secrets have no defaults and must be provided."""

    model_config = SettingsConfigDict(env_prefix="VIDGEN_", extra="ignore")

    # Secrets (no defaults)
    encryption_key: SecretStr
    index_key: SecretStr
    session_secret: SecretStr
    admin_password_hash: SecretStr

    # Infrastructure
    database_url: str = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen"
    redis_url: str = "redis://127.0.0.1:6379/0"
    storage_root: Path = Path("./media")
    ai_backend: Literal["fake", "real"] = "fake"

    # Upload limits
    max_video_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    max_video_seconds: float = Field(default=600.0, gt=0)
    min_video_seconds: float = Field(default=1.0, gt=0)
    max_sheet_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_sheet_rows: int = Field(default=100_000, gt=0)
    max_consent_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    # Row validation
    max_name_graphemes: int = Field(default=40, gt=0)

    # Audio timing
    crossfade_ms: int = Field(default=30, ge=20, le=50)
    max_stretch_ratio: float = Field(default=0.15, gt=0, lt=1)
    max_extension_seconds: float = Field(default=1.5, ge=0)
    duration_tolerance_ms: int = Field(default=50, ge=0)
    loudness_tolerance_lu: float = Field(default=1.0, gt=0)
    stt_confidence_threshold: float = Field(default=0.6, ge=0, le=1)

    # Queue behaviour
    row_timeout_seconds: int = Field(default=600, gt=0)
    retry_delay_seconds: int = Field(default=10, ge=0)
    max_retries: int = Field(default=1, ge=0)

    # Retention
    retention_days: int = Field(default=30, gt=0)

    # Output metadata
    creator_entity: str = "Dynamic Video Generator"

    # Auth
    login_max_failures: int = Field(default=5, gt=0)
    login_window_minutes: int = Field(default=15, gt=0)
    login_lockout_minutes: int = Field(default=15, gt=0)

    @model_validator(mode="after")
    def _check_duration_limits(self) -> Settings:
        """Ensure the minimum video length is below the maximum."""
        if self.min_video_seconds >= self.max_video_seconds:
            raise ValueError("min_video_seconds must be below max_video_seconds")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings; fails fast if a secret is missing."""
    return Settings()  # type: ignore[call-arg]
