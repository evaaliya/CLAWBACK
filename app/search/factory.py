"""Pick FakeSearch (tests / recorded / no key) or live TavilySearch."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.search.fake import FakeSearch
from app.search.tavily import TavilySearch


def build_search(settings: Settings) -> Any:
    cache = settings.cache_path() / "search"
    if settings.recorded_mode:
        return FakeSearch(cache)
    if settings.tavily_api_key:
        return TavilySearch(
            api_key=settings.tavily_api_key,
            cache_dir=cache,
        )
    return FakeSearch()
