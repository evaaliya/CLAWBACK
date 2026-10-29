"""T11 — Approve → outbox; refund accepted → savings event."""

from __future__ import annotations

import json

from app.claim_writer import accept_refund, approve_claim, prepare_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.rules import MINUTES_SAVED_PER_CLAIM
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


def test_approve_to_outbox_to_refund(conn, clock: Clock) -> None:
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
    prepared = prepare_claim(
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
    claim_id = prepared["claim_id"]

    approved = approve_claim(conn, claim_id=claim_id, clock=clock)
    conn.commit()
    assert approved["status"] == "sent"

    outbox = conn.execute(
        "SELECT claim_id, status, body FROM outbox WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    assert outbox is not None
    assert outbox["status"] == "queued"
    assert "subscription" in outbox["body"].lower() or "23500" in outbox["body"]

    claim = conn.execute(
        "SELECT status, approved_at FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()
    assert claim["status"] == "sent"
    assert claim["approved_at"] is not None

    refunded = accept_refund(conn, merchant="Replit", clock=clock)
    conn.commit()
    assert refunded["status"] == "refund_accepted"

    outbox2 = conn.execute(
        "SELECT status FROM outbox WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    assert outbox2["status"] == "refund_accepted"

    claim2 = conn.execute(
        "SELECT status, amount_recovered_cents FROM claims WHERE id = ?",
        (claim_id,),
    ).fetchone()
    assert claim2["status"] == "refund_accepted"
    assert claim2["amount_recovered_cents"] == 23500

    event = conn.execute(
        """
        SELECT kind, merchant, amount_cents, time_saved_min, source_id
        FROM savings_events WHERE source_id = ?
        """,
        (f"claim:{claim_id}",),
    ).fetchone()
    assert event is not None
    assert event["kind"] == "refund"
    assert event["merchant"] == "Replit"
    assert event["amount_cents"] == 23500
    assert event["time_saved_min"] == MINUTES_SAVED_PER_CLAIM
