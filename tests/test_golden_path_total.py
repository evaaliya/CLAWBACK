"""T18 — After the Golden Path the counter equals the sum of savings_events."""

from __future__ import annotations

import json

from app.claim_writer import accept_refund, approve_claim, prepare_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.savings.query import savings_summary
from app.search.fake import FakeSearch
from app.skill_forge.cancel import confirm_cancel, start_cancel


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

CLAIM_DRAFT = {
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

SETTINGS_PLAN = {
    "steps": [
        {"action": "open_settings", "note": "Settings"},
        {"action": "open_subscription", "note": "Subscription"},
        {"action": "manage_plan", "note": "Manage plan"},
        {"action": "end_plan", "note": "End plan"},
        {"action": "confirm_cancel", "note": "Requires user confirmation"},
        {"action": "save_confirmation", "note": "Store confirmation in memory"},
    ]
}


def _sub_id(conn, merchant: str) -> int:
    row = conn.execute(
        "SELECT id FROM subscriptions WHERE merchant = ?",
        (merchant,),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def _cancel(conn, clock: Clock, llm: FakeLLM, merchant: str) -> None:
    sub_id = _sub_id(conn, merchant)
    start_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    confirm_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()


def test_golden_path_total(seeded_conn, clock: Clock) -> None:
    conn = seeded_conn
    opening = savings_summary(conn)
    assert opening["amount_cents"] == 9_600
    assert opening["time_saved_min"] == 60

    llm = FakeLLM(
        recordings={
            "cancel:plan:StreamFlix": json.dumps(SETTINGS_PLAN),
            "cancel:plan:CloudNest": json.dumps(SETTINGS_PLAN),
            "claim:draft": json.dumps(CLAIM_DRAFT),
            "claim:validate": json.dumps({"ok": True, "reasons": []}),
        }
    )
    search = FakeSearch(
        recordings={"Replit return refund policy US": REPLIT_SOURCES}
    )

    # Cancel StreamFlix (Ultra → learn settings-menu) and CloudNest (skill reuse).
    _cancel(conn, clock, llm, "StreamFlix")
    _cancel(conn, clock, llm, "CloudNest")

    # Replit claim → approve → simulated refund.
    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('Replit', 'Core yearly subscription',
                '2026-09-30', 23500, 'USD', '2026-10-30', 'open')
        """
    )
    purchase_id = int(cur.lastrowid)
    conn.commit()

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
    approve_claim(conn, claim_id=claim_id, clock=clock)
    conn.commit()
    accept_refund(conn, merchant="Replit", clock=clock)
    conn.commit()

    # FitPulse via saved account-membership skill.
    _cancel(conn, clock, llm, "FitPulse")

    db_sum = conn.execute(
        """
        SELECT SUM(amount_cents) AS cents, SUM(time_saved_min) AS minutes
        FROM savings_events
        """
    ).fetchone()
    assert db_sum["cents"] == 84_700
    assert db_sum["minutes"] == 360

    counter = savings_summary(conn)
    assert counter["amount_cents"] == db_sum["cents"]
    assert counter["time_saved_min"] == db_sum["minutes"]
    assert counter["amount_cents"] == 84_700
    assert counter["time_saved_min"] == 360
