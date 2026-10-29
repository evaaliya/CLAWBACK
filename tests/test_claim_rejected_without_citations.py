"""T8 — A draft without citations is never shown."""

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


def test_claim_rejected_without_citations(conn, clock: Clock) -> None:
    purchase_id = _insert_replit(conn)
    search = FakeSearch(
        recordings={"Replit return refund policy US": REPLIT_SOURCES}
    )
    # Ultra returns a draft with empty citations — validator must reject; no row.
    llm = FakeLLM(
        recordings={
            "claim:draft": json.dumps(
                {
                    "text": (
                        "Please refund my Core yearly subscription "
                        "purchased on 2026-09-30 for 23500 cents."
                    ),
                    "citations": [],
                }
            ),
            "claim:draft:retry": json.dumps(
                {
                    "text": (
                        "Please refund my Core yearly subscription "
                        "purchased on 2026-09-30 for 23500 cents."
                    ),
                    "citations": [],
                }
            ),
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
    assert "claim_id" not in result or result.get("claim_id") is None
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM claims WHERE purchase_id = ?",
        (purchase_id,),
    ).fetchone()
    assert row["n"] == 0
