"""POST /chat — assemble reply + actionable cards from DB state."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

from app.agent_log import log_action
from app.clock import Clock
from app.deadline_watcher.scan import days_left
from app.rules import UNUSED_DAYS


def _soonest(return_deadline: str | None, warranty_until: str | None) -> date | None:
    candidates: list[date] = []
    for value in (return_deadline, warranty_until):
        if not value:
            continue
        try:
            candidates.append(date.fromisoformat(str(value)[:10]))
        except ValueError:
            continue
    return min(candidates) if candidates else None


def handle_chat(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    message: str,
) -> dict[str, Any]:
    """Return a short reply plus pending action cards (claims, deadlines, cancels)."""
    cards: list[dict[str, Any]] = []
    today = clock.today()

    cards.extend(_draft_claim_cards(conn, today))
    cards.extend(_deadline_cards(conn, today))
    cards.extend(_unused_subscription_cards(conn, today))

    text = (message or "").strip().lower()
    if not text or text in ("hi", "hello", "status", "help"):
        reply = _status_reply(conn, cards)
    elif "claim" in text or "refund" in text:
        reply = (
            "Here are open claim drafts."
            if any(c["type"] == "claim_draft" for c in cards)
            else "No claim drafts yet. Prepare one from a hot deadline."
        )
    elif "cancel" in text or "subscription" in text:
        reply = (
            "Unused subscriptions you can cancel:"
            if any(c["type"] == "cancel_plan" for c in cards)
            else "No unused subscriptions flagged right now."
        )
    else:
        reply = _status_reply(conn, cards)

    log_action(
        conn,
        clock,
        actor="chat",
        action="chat_reply",
        payload={"message_len": len(message or ""), "card_count": len(cards)},
    )
    return {"reply": reply, "cards": cards}


def _status_reply(conn: sqlite3.Connection, cards: list[dict[str, Any]]) -> str:
    savings = conn.execute(
        """
        SELECT COALESCE(SUM(amount_cents), 0) AS cents,
               COALESCE(SUM(time_saved_min), 0) AS minutes
        FROM savings_events
        """
    ).fetchone()
    cents = int(savings["cents"])
    dollars = cents // 100
    minutes = int(savings["minutes"])
    n = len(cards)
    if n:
        return (
            f"Recovered ${dollars} ({minutes} min). "
            f"You have {n} action card(s) waiting."
        )
    return f"Recovered ${dollars} ({minutes} min). Nothing urgent right now."


def _draft_claim_cards(conn: sqlite3.Connection, today: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.id, c.draft_text, c.sources_json, c.purchase_id,
               p.merchant, p.item, p.return_deadline, p.warranty_until
        FROM claims c
        JOIN purchases p ON p.id = c.purchase_id
        WHERE c.status = 'draft'
        ORDER BY c.id DESC
        """
    ).fetchall()
    cards: list[dict[str, Any]] = []
    for row in rows:
        sources = json.loads(row["sources_json"] or "[]")
        deadline = _soonest(row["return_deadline"], row["warranty_until"])
        left = days_left(deadline, today) if deadline else None
        cards.append(
            {
                "type": "claim_draft",
                "claim_id": int(row["id"]),
                "title": f"{row['merchant']}: {row['item']}",
                "body": row["draft_text"],
                "sources": [
                    {"title": s.get("title", ""), "url": s.get("url", "")}
                    for s in sources
                    if isinstance(s, dict)
                ],
                # UI labels approve as Send (T19 / D-025).
                "actions": ["approve", "reject"],
                "deadline_days": left,
            }
        )
    return cards


def _deadline_cards(conn: sqlite3.Connection, today: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, kind, purchase_id, payload_json
        FROM notifications
        WHERE seen_at IS NULL AND kind = 'deadline_alert'
        ORDER BY id DESC
        LIMIT 10
        """
    ).fetchall()
    cards: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        cards.append(
            {
                "type": "deadline_alert",
                "notification_id": int(row["id"]),
                "purchase_id": row["purchase_id"],
                "title": payload.get("title") or "Deadline alert",
                "body": payload.get("body") or payload.get("message") or "",
                "actions": ["Prepare claim"],
                "deadline_days": payload.get("days_left"),
            }
        )
    return cards


def _unused_subscription_cards(
    conn: sqlite3.Connection, today: date
) -> list[dict[str, Any]]:
    """Surface flagged / long-idle active subscriptions as cancel prompts."""
    rows = conn.execute(
        """
        SELECT id, merchant, amount_monthly_cents, last_used_at, status, portal_template
        FROM subscriptions
        WHERE status IN ('active', 'flagged')
        ORDER BY merchant
        """
    ).fetchall()
    cards: list[dict[str, Any]] = []
    for row in rows:
        last = row["last_used_at"]
        unused = False
        if row["status"] == "flagged":
            unused = True
        elif last:
            try:
                last_d = date.fromisoformat(str(last)[:10])
                unused = (today - last_d).days > UNUSED_DAYS
            except ValueError:
                unused = False
        if not unused:
            continue
        cards.append(
            {
                "type": "cancel_plan",
                "subscription_id": int(row["id"]),
                "merchant": row["merchant"],
                "title": f"Cancel {row['merchant']}?",
                "body": (
                    f"${row['amount_monthly_cents'] // 100}/mo · "
                    f"last used {row['last_used_at'] or 'unknown'}"
                ),
                "steps": [],
                "actions": ["Confirm"],
                "path": "pending",
            }
        )
    return cards
