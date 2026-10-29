"""T32 — Tavily policy query never contains personal data from the purchase."""

from __future__ import annotations

from app.privacy.redact import build_policy_query


def test_tavily_query_has_no_personal_data() -> None:
    purchase = {
        "merchant": "Replit",
        "buyer_name": "Aliya Karimova",
        "email": "aliya.k@example.com",
        "card_digits": "4417",
        "card_number": "4111 1111 1111 4417",
        "ship_to": "Aliya K., 12 Lenin St, Bishkek",
    }
    personal = [
        purchase["buyer_name"],
        purchase["email"],
        purchase["card_digits"],
        "4111",
        "Aliya",
        "aliya.k@example.com",
        "Lenin",
        "Bishkek",
    ]
    topics = (
        "return refund",  # refund path
        "warranty",
        "billing dispute duplicate charge",
    )
    for topic in topics:
        query = build_policy_query(
            purchase["merchant"], topic, "US"
        )
        assert purchase["merchant"] in query
        assert "policy" in query
        for fragment in personal:
            assert fragment not in query, f"{fragment!r} leaked into {query!r}"
