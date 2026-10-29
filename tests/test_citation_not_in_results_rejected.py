"""T9 — A citation URL not in the Tavily results is rejected."""

from __future__ import annotations

import json

from app.claim_writer import prepare_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.search.fake import FakeSearch


REPLIT_SOURCES = [
    {
        "title": "Am I eligible for a refund? | Replit",
        "url": "https://replit.com/help/answers/refunds",
        "excerpt": (
            "Subscription payments may be refunded within 30 days "
            "of purchase for a full refund to the original payment method."
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


def test_citation_not_in_results_rejected(conn, clock: Clock) -> None:
    purchase_id = _insert_replit(conn)
    search = FakeSearch(
        recordings={"Replit return refund policy US": REPLIT_SOURCES}
    )
    bad_url = "https://evil.example/not-from-tavily"
    draft = {
        "text": (
            "Please refund Core yearly subscription bought "
            "2026-09-30 for 23500 cents under the 30-day return policy."
        ),
        "citations": [
            {
                "title": "Replit refunds (not from Tavily)",
                "url": bad_url,
                "excerpt": "Subscription payments may be refunded within 30 days",
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
