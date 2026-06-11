"""Typed application configuration loaded from environment variables / .env.

Fails fast at access time if a required variable is missing, instead of producing
opaque errors deep in the pipeline.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Project-wide settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL connection used by SQLAlchemy and Alembic.
    database_url: str = Field(..., alias="DATABASE_URL")

    # Global random seed, persisted in every run's metadata (addendum §8).
    random_seed: int = Field(default=20260611, alias="RANDOM_SEED")

    # Directory holding immutable raw data snapshots.
    data_raw_dir: str = Field(default="data/raw", alias="DATA_RAW_DIR")


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment/.env
