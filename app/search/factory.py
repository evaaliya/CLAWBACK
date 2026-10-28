"""Pick FakeSearch (tests / recorded / no key) or live TavilySearch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import ROOT, Settings
from app.search.fake import FakeSearch
from app.search.tavily import TavilySearch


def recorded_search_path(settings: Settings | None = None) -> Path:
    """Golden Path cache: demo/recorded/search.json (SPEC §9 / T20)."""
    demo = Path(settings.demo_dir) if settings else ROOT / "demo"
    return demo / "recorded" / "search.json"


def build_search(settings: Settings) -> Any:
    cache = settings.cache_path() / "search"
    if settings.recorded_mode:
        return FakeSearch(recorded_search_path(settings))
    if settings.tavily_api_key:
        return TavilySearch(
            api_key=settings.tavily_api_key,
            cache_dir=cache,
        )
    return FakeSearch()
