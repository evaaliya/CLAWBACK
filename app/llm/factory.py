"""Pick FakeLLM (tests / recorded / no key) or live NebiusLLM."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.llm.fake import FakeLLM
from app.llm.nebius import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_NANO,
    DEFAULT_MODEL_SUPER,
    DEFAULT_MODEL_ULTRA,
    NebiusLLM,
)


def resolve_model_ids(settings: Settings) -> dict[str, str]:
    return {
        "nano": settings.model_nano or DEFAULT_MODEL_NANO,
        "super": settings.model_super or DEFAULT_MODEL_SUPER,
        "ultra": settings.model_ultra or DEFAULT_MODEL_ULTRA,
    }


def build_llm(settings: Settings) -> Any:
    cache = settings.cache_path() / "llm"
    if settings.recorded_mode:
        return FakeLLM(cache)
    if settings.nebius_api_key:
        return NebiusLLM(
            api_key=settings.nebius_api_key,
            base_url=settings.nebius_base_url or DEFAULT_BASE_URL,
        )
    # Offline without a key: same FakeLLM seam as tests.
    return FakeLLM()
