"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import rules

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nebius_api_key: str = ""
    nebius_base_url: str = ""
    model_nano: str = ""
    model_super: str = ""
    model_ultra: str = ""

    tavily_api_key: str = ""
    policy_jurisdiction: str = ""

    database_path: str = "./clawback.db"
    demo_today: str | None = "2026-10-27"
    recorded_mode: bool = False
    cache_dir: str = "./.cache"

    unused_days: int = Field(default=rules.UNUSED_DAYS)
    hot_deadline_days: int = Field(default=rules.HOT_DEADLINE_DAYS)
    minutes_saved_per_cancel: int = Field(default=rules.MINUTES_SAVED_PER_CANCEL)
    minutes_saved_per_claim: int = Field(default=rules.MINUTES_SAVED_PER_CLAIM)

    port: int = 8000
    demo_dir: str = str(ROOT / "demo")

    def database_file(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = ROOT / path
        return path

    def cache_path(self) -> Path:
        path = Path(self.cache_dir)
        if not path.is_absolute():
            path = ROOT / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
