"""POST /api/demo/reset — restore seeded demo state (e2e / recorded Golden Path)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request

from app.db import connect
from app.demo_reset import wipe_and_seed
from app.events import get_broker
from app.hardening.http import reject

router = APIRouter(tags=["demo"])

_REPLIT_SOURCES = [
    {
        "title": "Am I eligible for a refund? | Replit",
        "url": "https://replit.com/help/answers/refunds",
        "excerpt": "Subscription payments may be refunded within 30 days of purchase.",
    }
]


def _publish_all(*, demo_reset: bool = False) -> None:
    broker = get_broker()
    if demo_reset:
        broker.publish("demo.reset", {})
    broker.publish("savings.changed", {})
    broker.publish("subscription.changed", {})
    broker.publish("claim.changed", {})
    broker.publish("notification.new", {})
    broker.publish("skill.saved", {})


@router.post("/demo/reset")
def post_demo_reset(request: Request) -> dict:
    settings = request.app.state.settings
    if not settings.demo_reset_enabled():
        reject(
            "demo_reset_disabled",
            "Demo reset is disabled. Set DEMO_RESET=enabled to allow it.",
            status=403,
        )

    limiter = request.app.state.rate_limiter
    if not limiter.allow("demo_reset_global", limit=1, window_s=10.0):
        reject(
            "rate_limited",
            "Demo reset is limited to once per 10 seconds.",
            status=429,
        )

    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        counts = wipe_and_seed(conn, Path(settings.demo_dir), clock)
    finally:
        conn.close()
    _publish_all(demo_reset=True)
    return {"ok": True, "counts": counts}


@router.post("/demo/seed-claim")
def post_demo_seed_claim(request: Request) -> dict:
    """Insert a Replit draft claim for UI card tests (no LLM)."""
    settings = request.app.state.settings
    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        existing = conn.execute(
            """
            SELECT c.id FROM claims c
            JOIN purchases p ON p.id = c.purchase_id
            WHERE p.merchant = 'Replit' AND c.status = 'draft'
            """
        ).fetchone()
        if existing:
            return {"ok": True, "claim_id": int(existing["id"]), "seeded": False}

        purchase = conn.execute(
            "SELECT id FROM purchases WHERE merchant = 'Replit' LIMIT 1"
        ).fetchone()
        if purchase is None:
            cur = conn.execute(
                """
                INSERT INTO purchases
                    (merchant, item, date, amount_cents, currency,
                     return_deadline, status)
                VALUES ('Replit', 'Core yearly subscription',
                        '2026-09-30', 23500, 'USD', '2026-10-30', 'open')
                """
            )
            purchase_id = int(cur.lastrowid)
        else:
            purchase_id = int(purchase["id"])

        draft = (
            "Please refund my Core yearly subscription purchased on "
            "2026-09-30 for 23500 cents (USD). Your policy allows subscription "
            "payments to be refunded within 30 days. Subscription fee only."
        )
        cur = conn.execute(
            """
            INSERT INTO claims (purchase_id, draft_text, sources_json, status)
            VALUES (?, ?, ?, 'draft')
            """,
            (purchase_id, draft, json.dumps(_REPLIT_SOURCES, ensure_ascii=False)),
        )
        conn.commit()
        claim_id = int(cur.lastrowid)
    finally:
        conn.close()
    _publish_all()
    return {"ok": True, "claim_id": claim_id, "seeded": True}
