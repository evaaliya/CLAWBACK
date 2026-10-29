"""Pick FakeSearch (tests / recorded / no key) or live TavilySearch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import ROOT, Settings
from app.hardening.budget import BudgetAwareSearch, LiveBudget
from app.search.fake import FakeSearch
from app.search.tavily import TavilySearch


def recorded_search_path(settings: Settings | None = None) -> Path:
    """Golden Path cache: demo/recorded/search.json (SPEC §9 / T20)."""
    demo = Path(settings.demo_dir) if settings else ROOT / "demo"
    return demo / "recorded" / "search.json"


def build_search(
    settings: Settings,
    *,
    budget: LiveBudget | None = None,
) -> Any:
    cache = settings.cache_path() / "search"
    recorded = FakeSearch(recorded_search_path(settings))
    if settings.recorded_mode:
        return recorded
    if settings.tavily_api_key:
        live = TavilySearch(
            api_key=settings.tavily_api_key,
            cache_dir=cache,
        )
        if budget is not None:
            return BudgetAwareSearch(
                live=live,
                recorded=recorded,
                budget=budget,
                force_recorded=False,
            )
        return live
    return FakeSearch()
