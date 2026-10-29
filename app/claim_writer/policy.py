"""web_search_policy tool — Tavily (or FakeSearch) for merchant return policy."""

from __future__ import annotations

import sqlite3
from typing import Any, Protocol

from app.agent_log import log_action
from app.clock import Clock
from app.privacy.redact import build_policy_query
from app.privacy.trace import search_traced


class SearchClient(Protocol):
    def search(self, query: str, **params: Any) -> list[dict[str, Any]]: ...


def policy_query(merchant: str, jurisdiction: str, topic: str = "return refund") -> str:
    """Backward-compatible wrapper; prefer build_policy_query(merchant, topic, jurisdiction)."""
    return build_policy_query(merchant, topic, jurisdiction)


def web_search_policy(
    conn: sqlite3.Connection,
    clock: Clock,
    search: SearchClient,
    *,
    merchant: str,
    topic: str = "return refund",
    jurisdiction: str = "",
) -> list[dict[str, Any]]:
    query = build_policy_query(merchant, topic, jurisdiction)
    results = search_traced(
        conn,
        clock,
        search,
        query=query,
        role="policy",
        model="tavily",
    )
    sources = [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "excerpt": r.get("excerpt") or r.get("content") or "",
        }
        for r in results
    ]
    log_action(
        conn,
        clock,
        actor="claim_writer",
        action="web_search_policy",
        payload={
            "merchant": merchant,
            "topic": topic,
            "jurisdiction": jurisdiction,
            "query": query,
            "result_count": len(sources),
            "urls": [s["url"] for s in sources if s["url"]],
        },
    )
    return sources
