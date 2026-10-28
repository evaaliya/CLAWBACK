"""Claim draft validator (SPEC §4.4). Any failure → reject."""

from __future__ import annotations

from typing import Any


def validate_draft(
    *,
    draft: dict[str, Any],
    purchase: dict[str, Any],
    session_sources: list[dict[str, Any]],
) -> list[str]:
    """Return a list of failure reasons; empty means pass."""
    reasons: list[str] = []
    citations = draft.get("citations")
    text = draft.get("text") or ""

    if not isinstance(citations, list) or len(citations) < 1:
        reasons.append("at least one citation is required")
        return reasons

    session_urls = {
        (s.get("url") or "").rstrip("/")
        for s in session_sources
        if s.get("url")
    }
    session_excerpts = [
        (s.get("excerpt") or "").strip()
        for s in session_sources
        if (s.get("excerpt") or "").strip()
    ]

    for i, cite in enumerate(citations):
        if not isinstance(cite, dict):
            reasons.append(f"citation[{i}] is not an object")
            continue
        url = (cite.get("url") or "").rstrip("/")
        if not url or url not in session_urls:
            reasons.append(f"citation[{i}] url not in session Tavily results")
        excerpt = (cite.get("excerpt") or "").strip()
        if not excerpt:
            reasons.append(f"citation[{i}] missing excerpt")
        elif not _excerpt_supported(excerpt, session_excerpts):
            reasons.append(f"citation[{i}] excerpt not supported by search results")

    # Purchase facts must appear in the draft text.
    item = str(purchase.get("item") or "")
    purchase_date = str(purchase.get("date") or "")
    amount = purchase.get("amount_cents")
    if item and item not in text:
        reasons.append("draft text missing purchase item")
    if purchase_date and purchase_date not in text:
        reasons.append("draft text missing purchase date")
    if amount is not None and str(amount) not in text and not _amount_as_dollars_in_text(
        int(amount), text
    ):
        reasons.append("draft text missing purchase amount")

    return reasons


def _excerpt_supported(excerpt: str, session_excerpts: list[str]) -> bool:
    needle = excerpt.lower()
    for source in session_excerpts:
        hay = source.lower()
        if needle in hay or hay in needle:
            return True
        # Allow substantial overlap on the first ~40 chars.
        if len(needle) >= 40 and needle[:40] in hay:
            return True
    return False


def _amount_as_dollars_in_text(amount_cents: int, text: str) -> bool:
    dollars = amount_cents / 100
    forms = {
        f"${dollars:.2f}",
        f"${dollars:.0f}" if amount_cents % 100 == 0 else "",
        f"{dollars:.2f}",
        str(amount_cents),
    }
    return any(form and form in text for form in forms)
