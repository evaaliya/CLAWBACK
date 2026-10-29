"""Citation domain/title must match the purchase merchant or the draft is rejected."""

from __future__ import annotations

import json

from app.claim_writer import prepare_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.search.fake import FakeSearch


FOREIGN_SOURCES = [
    {
        "title": "Amazon Returns and Refunds",
        "url": "https://www.amazon.com/gp/help/customer/display.html",
        "excerpt": (
            "Most items can be returned within 30 days of receipt "
            "for a full refund to the original payment method."
        ),
    }
]


def _insert_replit(conn) -> int:
    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('Replit', 'Core yearly subscription',
                '2026-09-30', 23500, 'USD', '2026-10-30', 'open')
        """
    )
    conn.commit()
    return int(cur.lastrowid)


def test_citation_must_match_merchant(conn, clock: Clock) -> None:
    purchase_id = _insert_replit(conn)
    search = FakeSearch(
        recordings={"Replit return refund policy US": FOREIGN_SOURCES}
    )
    draft = {
        "text": (
            "Please refund my Core yearly subscription purchased on "
            "2026-09-30 for 23500 cents (USD) under the 30-day return policy."
        ),
        "citations": [
            {
                "title": "Amazon Returns and Refunds",
                "url": "https://www.amazon.com/gp/help/customer/display.html",
                "excerpt": (
                    "Most items can be returned within 30 days of receipt "
                    "for a full refund to the original payment method."
                ),
            }
        ],
    }
    llm = FakeLLM(
        recordings={
            "claim:draft": json.dumps(draft),
            "claim:draft:retry": json.dumps(draft),
            "claim:validate": json.dumps({"ok": True, "reasons": []}),
        }
    )

    result = prepare_claim(
        conn,
        purchase_id=purchase_id,
        search=search,
        llm=llm,
        clock=clock,
        jurisdiction="US",
        model_ultra="ultra",
        model_super="super",
    )
    conn.commit()

    assert result["ok"] is False
    assert result["card"]["type"] == "error"
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM claims WHERE purchase_id = ?",
        (purchase_id,),
    ).fetchone()
    assert row["n"] == 0
