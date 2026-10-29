"""Claim draft validator (SPEC §4.4). Any failure → reject."""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

_WINDOW_DAYS = re.compile(r"(\d+)\s*-?\s*days?", re.IGNORECASE)


def source_matches_merchant(source: dict[str, Any], merchant: str) -> bool:
    """True when source title or URL host corresponds to the purchase merchant."""
    token = _merchant_token(merchant)
    if not token:
        return False
    title = str(source.get("title") or "")
    if token in _alnum(title) or merchant.strip().lower() in title.lower():
        return True
    host = _url_host(str(source.get("url") or ""))
    if not host:
        return False
    if token in _alnum(host) or token in host.lower():
        return True
    return False


def validate_draft(
    *,
    draft: dict[str, Any],
    purchase: dict[str, Any],
    session_sources: list[dict[str, Any]],
    as_of: date | None = None,
) -> list[str]:
    """Return a list of failure reasons; empty means pass."""
    reasons: list[str] = []
    citations = draft.get("citations")
    text = draft.get("text") or ""
    merchant = str(purchase.get("merchant") or "")

    if not isinstance(citations, list) or len(citations) < 1:
        reasons.append("at least one citation is required")
        return reasons

    # Discard sources that do not match the merchant (domain or title).
    matched = [
        c
        for c in citations
        if isinstance(c, dict) and source_matches_merchant(c, merchant)
    ]
    if not matched:
        reasons.append("no citation matches merchant")
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

    for i, cite in enumerate(matched):
        url = (cite.get("url") or "").rstrip("/")
        if not url or url not in session_urls:
            reasons.append(f"citation[{i}] url not in session Tavily results")
        excerpt = (cite.get("excerpt") or "").strip()
        if not excerpt:
            reasons.append(f"citation[{i}] missing excerpt")
        elif not _excerpt_supported(excerpt, session_excerpts):
            reasons.append(f"citation[{i}] excerpt not supported by search results")

    window_days = _extract_window_days(
        [(c.get("excerpt") or "") for c in matched]
    )
    if window_days is not None and as_of is not None:
        purchase_date_raw = purchase.get("date")
        if purchase_date_raw:
            purchase_date = date.fromisoformat(str(purchase_date_raw))
            days_since = (as_of - purchase_date).days
            if days_since > window_days:
                reasons.append("purchase is outside the cited refund window")

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


def _merchant_token(merchant: str) -> str:
    return _alnum(merchant)


def _alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _url_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _extract_window_days(excerpts: list[str]) -> int | None:
    found: list[int] = []
    for excerpt in excerpts:
        for match in _WINDOW_DAYS.finditer(excerpt):
            found.append(int(match.group(1)))
    return max(found) if found else None


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
