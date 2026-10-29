"""Trace LLM and search calls into agent_log without storing raw prompts."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Protocol

from app.agent_log import log_action
from app.clock import Clock
from app.privacy.redact import scrub_for_model


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


class SearchClient(Protocol):
    def search(self, query: str, **params: Any) -> list[dict[str, Any]]: ...


def complete_traced(
    conn: sqlite3.Connection,
    clock: Clock,
    llm: LLMClient,
    *,
    role: str,
    model: str,
    messages: list[dict[str, Any]] | None = None,
    prompt: str | None = None,
    recorded: bool | None = None,
    **kwargs: Any,
) -> Any:
    """Call llm.complete and write an `llm_call` row (no raw prompt text)."""
    t0 = time.perf_counter()
    result = llm.complete(
        model=model, messages=messages, prompt=prompt, **kwargs
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    usage = getattr(llm, "last_usage", None) or {}
    prompt_tokens = int(
        usage.get("prompt_tokens")
        or _estimate_prompt_tokens(prompt=prompt, messages=messages)
    )
    completion_tokens = int(
        usage.get("completion_tokens") or _estimate_completion_tokens(result)
    )
    is_recorded = (
        recorded
        if recorded is not None
        else bool(getattr(llm, "using_recorded", False))
        or _looks_recorded(llm)
    )
    log_action(
        conn,
        clock,
        actor="llm",
        action="llm_call",
        payload={
            "role": role,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
            "recorded": is_recorded,
        },
    )
    return result


def search_traced(
    conn: sqlite3.Connection,
    clock: Clock,
    search: SearchClient,
    *,
    query: str,
    role: str = "policy",
    model: str = "tavily",
    recorded: bool | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Call search.search and write a `search_call` row with the redacted query."""
    redacted_query = scrub_for_model(query)
    t0 = time.perf_counter()
    results = search.search(query, **params)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    is_recorded = (
        recorded
        if recorded is not None
        else bool(getattr(search, "using_recorded", False))
        or _looks_recorded(search)
    )
    log_action(
        conn,
        clock,
        actor="search",
        action="search_call",
        payload={
            "role": role,
            "model": model,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": latency_ms,
            "recorded": is_recorded,
            "query": redacted_query,
            "result_count": len(results),
        },
    )
    return results


def _looks_recorded(client: Any) -> bool:
    name = type(client).__name__.lower()
    return "fake" in name


def _estimate_prompt_tokens(
    *,
    prompt: str | None,
    messages: list[dict[str, Any]] | None,
) -> int:
    if prompt:
        return max(1, len(prompt) // 4)
    if messages:
        blob = json.dumps(messages, ensure_ascii=False)
        return max(1, len(blob) // 4)
    return 0


def _estimate_completion_tokens(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, str):
        return max(1, len(result) // 4) if result else 0
    try:
        blob = json.dumps(result, ensure_ascii=False)
    except TypeError:
        blob = str(result)
    return max(1, len(blob) // 4) if blob else 0
