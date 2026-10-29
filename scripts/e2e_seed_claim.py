#!/usr/bin/env python3
"""Insert a Replit draft claim for e2e_claim_card (no LLM required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.clock import clock_from_settings
from app.config import get_settings
from app.db import connect, init_db


SOURCES = [
    {
        "title": "Am I eligible for a refund? | Replit",
        "url": "https://replit.com/help/answers/refunds",
        "excerpt": "Subscription payments may be refunded within 30 days of purchase.",
    }
]


def main() -> None:
    settings = get_settings()
    clock = clock_from_settings(settings.demo_today)
    conn = connect(settings.database_file())
    try:
        init_db(conn)
        existing = conn.execute(
            """
            SELECT c.id FROM claims c
            JOIN purchases p ON p.id = c.purchase_id
            WHERE p.merchant = 'Replit' AND c.status = 'draft'
            """
        ).fetchone()
        if existing:
            print(f"draft claim already present: {existing['id']}")
            return

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
            (purchase_id, draft, json.dumps(SOURCES, ensure_ascii=False)),
        )
        conn.commit()
        print(f"seeded draft claim {cur.lastrowid} at {clock.now().isoformat()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
