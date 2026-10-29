"""Allowlist policy queries and scrub personal data before model egress."""

from __future__ import annotations

import re

# Topics the claim / search paths may pass into build_policy_query.
# Free text from receipts or chat must never become a topic string here —
# callers pass one of these (or a short allowlisted phrase they own).
ALLOWED_POLICY_TOPICS = frozenset(
    {
        "return refund",
        "warranty",
        "billing dispute duplicate charge",
    }
)

_CARD_LONG = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_CARD_LAST4 = re.compile(
    r"(?i)\b(?:card\s*(?:ending|ends?|number|no\.?|#)?\s*(?:in\s+|with\s+|:\s*)?|"
    r"(?:ending|ends)\s+(?:in\s+)?)(\d{4})\b"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"
)
_PII_LINE = re.compile(
    r"(?im)^(\s*(?:ship\s*to|bill\s*to|sold\s*to|customer|name|recipient)\s*:).+$"
)
_STREET = re.compile(
    r"(?i)\b\d{1,6}\s+(?:[A-Za-z0-9.-]+\s+){0,6}"
    r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|lane|ln\.?|"
    r"drive|dr\.?|court|ct\.?|way|place|pl\.?)\b"
)


def build_policy_query(merchant: str, topic: str, jurisdiction: str) -> str:
    """Build a Tavily query from exactly three allowlisted fields.

    Never concatenate free-text purchase/receipt content. Merchant and
    jurisdiction are stripped to short safe tokens; topic must be one of
    ALLOWED_POLICY_TOPICS (or is coerced to the default refund topic).
    """
    merchant_s = _safe_token(merchant, max_len=64)
    topic_s = topic.strip().lower() if topic else ""
    if topic_s not in ALLOWED_POLICY_TOPICS:
        topic_s = "return refund"
    jurisdiction_s = _safe_token(jurisdiction, max_len=16)
    parts = [merchant_s, topic_s, "policy"]
    if jurisdiction_s:
        parts.append(jurisdiction_s)
    return " ".join(p for p in parts if p)


def scrub_for_model(text: str) -> str:
    """Mask card digits, email, phone, street addresses, and Ship-to lines.

    Raw text stays in local `documents`; only the scrubbed copy may go to a model.
    """
    if not text:
        return text
    out = text
    out = _PII_LINE.sub(r"\1 [REDACTED]", out)
    out = _EMAIL.sub("[EMAIL]", out)
    out = _CARD_LONG.sub("[CARD]", out)
    out = _CARD_LAST4.sub(
        lambda m: m.group(0)[: -len(m.group(1))] + "[LAST4]", out
    )
    out = _PHONE.sub("[PHONE]", out)
    out = _STREET.sub("[ADDRESS]", out)
    return out


def _safe_token(value: str, *, max_len: int) -> str:
    """Keep merchant/jurisdiction as short alphanumeric tokens; drop PII-like runs."""
    if not value:
        return ""
    # Drop emails / long digit runs before taking a token.
    cleaned = _EMAIL.sub("", value)
    cleaned = _CARD_LONG.sub("", cleaned)
    cleaned = re.sub(r"\d{4,}", "", cleaned)
    cleaned = re.sub(r"[^\w\s&.+-]+", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len].strip()
