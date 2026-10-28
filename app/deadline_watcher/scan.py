"""scan(now) per SPEC §4.3 — hot deadlines, expire past ones, notify once per day."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

from app.agent_log import log_action
from app.clock import Clock
from app.rules import HOT_DEADLINE_DAYS

SKIP_CLAIM_STATUSES = frozenset({"sent", "refund_accepted", "rejected"})
NOTIFICATION_KIND = "deadline_alert"


def days_left(deadline: date, today: date) -> int:
    """UTC calendar days remaining until deadline (negative if past)."""
    return (deadline - today).days


def is_hot(days: int, hot_deadline_days: int = HOT_DEADLINE_DAYS) -> bool:
    """Hot when 0 ≤ days_left ≤ HOT_DEADLINE_DAYS."""
    return 0 <= days <= hot_deadline_days


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _soonest_deadline(
    return_deadline: str | None, warranty_until: str | None
) -> date | None:
    candidates = [
        d for d in (_parse_date(return_deadline), _parse_date(warranty_until)) if d
    ]
    if not candidates:
        return None
    return min(candidates)


def _has_blocking_claim(conn: sqlite3.Connection, purchase_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1 AS ok FROM claims
        WHERE purchase_id = ? AND status IN ('sent', 'refund_accepted', 'rejected')
        LIMIT 1
        """,
        (purchase_id,),
    ).fetchone()
    return row is not None


def _deadline_alert_payload(
    purchase: sqlite3.Row,
    *,
    days: int,
    deadline: date,
) -> dict[str, Any]:
    window = "return window" if purchase["return_deadline"] else "warranty"
    if days == 0:
        body = f"{window} closes today"
    elif days == 1:
        body = f"{window} closes in 1 day"
    else:
        body = f"{window} closes in {days} days"
    return {
        "type": NOTIFICATION_KIND,
        "purchase_id": purchase["id"],
        "title": purchase["item"],
        "body": body,
        "merchant": purchase["merchant"],
        "item": purchase["item"],
        "amount_cents": purchase["amount_cents"],
        "currency": purchase["currency"],
        "days_left": days,
        "deadline": deadline.isoformat(),
        "actions": ["Prepare claim"],
    }


def scan(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    hot_deadline_days: int = HOT_DEADLINE_DAYS,
) -> dict[str, Any]:
    """
    Pure function of DB + clock: expire past deadlines, notify hot ones once per day.
    Never creates, approves, or sends a claim.
    """
    today = clock.today()
    day_s = today.isoformat()
    created_at = clock.now().isoformat()

    purchases = conn.execute(
        """
        SELECT id, merchant, item, date, amount_cents, currency,
               return_deadline, warranty_until, status
        FROM purchases
        WHERE status = 'open'
          AND (return_deadline IS NOT NULL OR warranty_until IS NOT NULL)
        ORDER BY id
        """
    ).fetchall()

    notifications: list[dict[str, Any]] = []
    expired_ids: list[int] = []
    created = 0

    for purchase in purchases:
        deadline = _soonest_deadline(
            purchase["return_deadline"], purchase["warranty_until"]
        )
        if deadline is None:
            continue

        left = days_left(deadline, today)

        if left < 0:
            conn.execute(
                "UPDATE purchases SET status = 'expired' WHERE id = ? AND status = 'open'",
                (purchase["id"],),
            )
            expired_ids.append(purchase["id"])
            continue

        if _has_blocking_claim(conn, purchase["id"]):
            continue

        if not is_hot(left, hot_deadline_days):
            continue

        payload = _deadline_alert_payload(purchase, days=left, deadline=deadline)
        payload_json = json.dumps(payload, ensure_ascii=False)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO notifications
                (kind, purchase_id, day, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (NOTIFICATION_KIND, purchase["id"], day_s, payload_json, created_at),
        )
        if cur.rowcount == 1:
            created += 1
            notifications.append(
                {
                    "purchase_id": purchase["id"],
                    "days_left": left,
                    "payload": payload,
                }
            )

    log_action(
        conn,
        clock,
        actor="deadline_watcher",
        action="scan",
        payload={
            "day": day_s,
            "created": created,
            "expired": expired_ids,
            "notified_purchase_ids": [n["purchase_id"] for n in notifications],
        },
    )

    return {
        "day": day_s,
        "created": created,
        "expired": expired_ids,
        "notifications": notifications,
    }


def list_deadlines(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    hot_deadline_days: int = HOT_DEADLINE_DAYS,
) -> list[dict[str, Any]]:
    """Purchases with a deadline, sorted by urgency (soonest first)."""
    today = clock.today()
    rows = conn.execute(
        """
        SELECT id, merchant, item, date, amount_cents, currency,
               return_deadline, warranty_until, status
        FROM purchases
        WHERE return_deadline IS NOT NULL OR warranty_until IS NOT NULL
        """
    ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        deadline = _soonest_deadline(row["return_deadline"], row["warranty_until"])
        if deadline is None:
            continue
        left = days_left(deadline, today)
        items.append(
            {
                "id": row["id"],
                "merchant": row["merchant"],
                "item": row["item"],
                "date": row["date"],
                "amount_cents": row["amount_cents"],
                "currency": row["currency"],
                "return_deadline": row["return_deadline"],
                "warranty_until": row["warranty_until"],
                "status": row["status"],
                "deadline": deadline.isoformat(),
                "days_left": left,
                "hot": is_hot(left, hot_deadline_days),
            }
        )

    items.sort(key=lambda x: (x["days_left"], x["id"]))
    return items
