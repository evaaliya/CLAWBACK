"""Execute mock portal actions with a confirm_cancel approval gate."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.agent_log import log_action
from app.clock import Clock
from app.portal.templates import TEMPLATE_STEPS, account_payload, help_payload
from app.portal.errors import ActionUnavailable, ApprovalRequired


def get_portal_account(conn: sqlite3.Connection, merchant: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT merchant, portal_template, status, confirmation_no
        FROM portal_accounts WHERE lower(merchant) = lower(?)
        """,
        (merchant,),
    ).fetchone()
    if row is None:
        raise KeyError(f"portal account not found for {merchant}")
    return dict(row)


def get_account_view(conn: sqlite3.Connection, merchant: str) -> dict[str, Any]:
    account = get_portal_account(conn, merchant)
    payload = account_payload(
        account["merchant"], account["portal_template"], account["status"]
    )
    payload["available_actions"] = available_actions(conn, merchant)
    return payload


def get_help_cancel(conn: sqlite3.Connection, merchant: str) -> dict[str, Any]:
    account = get_portal_account(conn, merchant)
    return help_payload(account["merchant"], account["portal_template"])


def get_status(conn: sqlite3.Connection, merchant: str) -> dict[str, Any]:
    account = get_portal_account(conn, merchant)
    return {
        "merchant": account["merchant"],
        "status": account["status"],
        "confirmation_no": account["confirmation_no"],
        "portal_template": account["portal_template"],
    }


def available_actions(conn: sqlite3.Connection, merchant: str) -> list[str]:
    account = get_portal_account(conn, merchant)
    steps = TEMPLATE_STEPS.get(account["portal_template"], [])
    if not steps:
        return []
    done = _completed_steps(conn, account["merchant"])
    if len(done) >= len(steps):
        return []
    next_action = steps[len(done)]
    # confirm_cancel flips status to cancelled; save_confirmation may still follow.
    if account["status"] == "cancelled" and next_action != "save_confirmation":
        return []
    return [next_action]


def has_cancel_approval(conn: sqlite3.Connection, merchant: str) -> bool:
    rows = conn.execute(
        """
        SELECT id, action, payload_json FROM agent_log
        WHERE action IN ('cancel_confirmed', 'portal_step')
        ORDER BY id ASC
        """
    ).fetchall()
    pending = False
    for row in rows:
        payload = json.loads(row["payload_json"])
        if str(payload.get("merchant", "")).lower() != merchant.lower():
            continue
        if row["action"] == "cancel_confirmed":
            pending = True
        elif (
            row["action"] == "portal_step"
            and payload.get("action") == "confirm_cancel"
            and payload.get("ok")
        ):
            pending = False
    return pending


def record_cancel_approval(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    merchant: str,
    subscription_id: int,
) -> None:
    log_action(
        conn,
        clock,
        actor="user",
        action="cancel_confirmed",
        payload={"merchant": merchant, "subscription_id": subscription_id},
    )


def perform_action(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    merchant: str,
    action: str,
) -> dict[str, Any]:
    account = get_portal_account(conn, merchant)
    available = available_actions(conn, merchant)
    if action not in available:
        raise ActionUnavailable(
            merchant=account["merchant"],
            action=action,
            reason=f"not available; next={available}",
        )

    if action == "confirm_cancel" and not has_cancel_approval(conn, merchant):
        raise ApprovalRequired(merchant=account["merchant"])

    confirmation_no = account["confirmation_no"]
    status = account["status"]
    if action == "confirm_cancel":
        confirmation_no = _make_confirmation_no(account["merchant"], clock)
        status = "cancelled"
        conn.execute(
            """
            UPDATE portal_accounts
            SET status = 'cancelled', confirmation_no = ?
            WHERE merchant = ?
            """,
            (confirmation_no, account["merchant"]),
        )

    log_action(
        conn,
        clock,
        actor="portal",
        action="portal_step",
        payload={
            "merchant": account["merchant"],
            "action": action,
            "ok": True,
            "status": status,
        },
    )

    return {
        "merchant": account["merchant"],
        "action": action,
        "ok": True,
        "status": status,
        "confirmation_no": confirmation_no,
        "available_actions": available_actions(conn, merchant),
    }


def _completed_steps(conn: sqlite3.Connection, merchant: str) -> list[str]:
    """In-order portal steps for the latest cancel attempt on this merchant."""
    account = get_portal_account(conn, merchant)
    steps = TEMPLATE_STEPS.get(account["portal_template"], [])
    if not steps:
        return []

    rows = conn.execute(
        """
        SELECT payload_json FROM agent_log
        WHERE actor = 'portal' AND action = 'portal_step'
        ORDER BY id ASC
        """
    ).fetchall()

    completed: list[str] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if str(payload.get("merchant", "")).lower() != merchant.lower():
            continue
        action = payload.get("action")
        if not payload.get("ok") or action == "__abandon__":
            completed = []
            continue
        if not isinstance(action, str):
            continue
        if action == steps[0]:
            completed = [action]
        elif completed and len(completed) < len(steps) and action == steps[len(completed)]:
            completed.append(action)
    return completed


def _make_confirmation_no(merchant: str, clock: Clock) -> str:
    slug = "".join(ch.upper() if ch.isalnum() else "" for ch in merchant)[:6] or "MRCH"
    day = clock.today().isoformat().replace("-", "")
    return f"CB-{slug}-{day}"
