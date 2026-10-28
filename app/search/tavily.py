"""Tavily Search client (live).

Docs: https://docs.tavily.com/documentation/api-reference/endpoint/search
Nebius cookbooks use max_results=5 and search_depth advanced|basic.
Maps results[].content → excerpt for Clawback's source shape.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from app.search.fake import search_hash

DEFAULT_BASE_URL = "https://api.tavily.com"
DEFAULT_SEARCH_DEPTH = "basic"
DEFAULT_MAX_RESULTS = 5


class TavilySearch:
    """POST /search with Bearer auth; optional disk cache by request hash."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: Path | None = None,
        search_depth: str = DEFAULT_SEARCH_DEPTH,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("TAVILY_API_KEY is required for TavilySearch")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.search_depth = search_depth
        self.max_results = max_results
        self.timeout = timeout
        self.cache_dir = cache_dir
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls: list[dict[str, Any]] = []
        self.call_counts: Counter[str] = Counter()

    def search(self, query: str, **params: Any) -> list[dict[str, Any]]:
        depth = params.pop("search_depth", self.search_depth)
        max_results = params.pop("max_results", self.max_results)
        key_params = {"search_depth": depth, "max_results": max_results, **params}
        key = search_hash(query, **key_params)
        self.calls.append({"key": key, "query": query, **key_params})
        self.call_counts["search"] += 1

        cached = self._read_cache(key)
        if cached is not None:
            return cached

        body = {
            "query": query,
            "search_depth": depth,
            "max_results": max_results,
            **params,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            payload = response.json()

        results = [_normalize_result(item) for item in payload.get("results") or []]
        self._write_cache(key, results)
        return results

    def _read_cache(self, key: str) -> list[dict[str, Any]] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        if not path.is_file():
            return None
        return list(json.loads(path.read_text(encoding="utf-8")))

    def _write_cache(self, key: str, results: list[dict[str, Any]]) -> None:
        if self.cache_dir is None:
            return
        path = self.cache_dir / f"{key}.json"
        path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    excerpt = item.get("excerpt")
    if excerpt is None:
        excerpt = item.get("content") or ""
    return {
        "title": item.get("title") or "",
        "url": item.get("url") or "",
        "excerpt": excerpt,
    }
