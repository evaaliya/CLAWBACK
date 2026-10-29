"""Pick FakeLLM (tests / recorded / no key) or live NebiusLLM."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import ROOT, Settings
from app.hardening.budget import BudgetAwareLLM, LiveBudget
from app.llm.fake import FakeLLM
from app.llm.nebius import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_NANO,
    DEFAULT_MODEL_SUPER,
    DEFAULT_MODEL_ULTRA,
    NebiusLLM,
)


def recorded_llm_path(settings: Settings | None = None) -> Path:
    """Golden Path cache: demo/recorded/llm.json (SPEC §9 / T20)."""
    demo = Path(settings.demo_dir) if settings else ROOT / "demo"
    return demo / "recorded" / "llm.json"


def resolve_model_ids(settings: Settings) -> dict[str, str]:
    return {
        "nano": settings.model_nano or DEFAULT_MODEL_NANO,
        "super": settings.model_super or DEFAULT_MODEL_SUPER,
        "ultra": settings.model_ultra or DEFAULT_MODEL_ULTRA,
    }


def build_llm(
    settings: Settings,
    *,
    budget: LiveBudget | None = None,
) -> Any:
    recorded = FakeLLM(recorded_llm_path(settings))
    if settings.recorded_mode:
        return recorded
    if settings.nebius_api_key:
        live = NebiusLLM(
            api_key=settings.nebius_api_key,
            base_url=settings.nebius_base_url or DEFAULT_BASE_URL,
        )
        if budget is not None:
            return BudgetAwareLLM(
                live=live,
                recorded=recorded,
                budget=budget,
                force_recorded=False,
            )
        return live
    # Offline without a key: same FakeLLM seam as tests.
    return FakeLLM()
