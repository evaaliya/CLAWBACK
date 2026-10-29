"""T10 — Nothing is sent without approval."""

from __future__ import annotations

import json
import pytest

from app.claim_writer import ApprovalRequired, prepare_claim, send_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.search.fake import FakeSearch


REPLIT_SOURCES = [
    {
        "title": "Am I eligible for a refund? | Replit",
        "url": "https://replit.com/help/answers/refunds",
        "excerpt": (
            "Subscription payments may be refunded within 30 days "
            "of purchase for a full refund to the original payment method. "
            "Contact support with your order number."
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


def _good_draft() -> dict:
    return {
        "text": (
            "Please refund my Core yearly subscription purchased on "
            "2026-09-30 for 23500 cents (USD). Your policy allows subscription "
            "payments to be refunded within 30 days. Subscription fee only."
        ),
        "citations": [
            {
                "title": "Am I eligible for a refund? | Replit",
                "url": "https://replit.com/help/answers/refunds",
                "excerpt": (
                    "Subscription payments may be refunded within 30 days "
                    "of purchase for a full refund to the original payment method."
                ),
            }
        ],
    }


def test_send_requires_approval(conn, clock: Clock) -> None:
    purchase_id = _insert_replit(conn)
    search = FakeSearch(
        recordings={"Replit return refund policy US": REPLIT_SOURCES}
    )
    llm = FakeLLM(
        recordings={
            "claim:draft": json.dumps(_good_draft()),
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
    assert result["ok"] is True
    claim_id = result["claim_id"]

    with pytest.raises(ApprovalRequired):
        send_claim(conn, claim_id=claim_id, clock=clock)

    outbox = conn.execute("SELECT COUNT(*) AS n FROM outbox").fetchone()
    assert outbox["n"] == 0
    status = conn.execute(
        "SELECT status FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()["status"]
    assert status == "draft"
