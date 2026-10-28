"""Claim state machine: draft → approved → sent → refund_accepted | rejected."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.agent_log import log_action
from app.claim_writer.errors import ApprovalRequired
from app.clock import Clock
from app.rules import MINUTES_SAVED_PER_CLAIM
from app.savings import record_savings


def approve_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: int,
    clock: Clock,
) -> dict[str, Any]:
    claim = _get_claim(conn, claim_id)
    if claim is None:
        raise KeyError(f"claim {claim_id} not found")
    if claim["status"] not in ("draft", "approved"):
        raise ValueError(f"cannot approve claim in status {claim['status']}")

    now = clock.now().isoformat()
    conn.execute(
        """
        UPDATE claims
        SET status = 'approved', approved_at = ?
        WHERE id = ?
        """,
        (now, claim_id),
    )
    log_action(
        conn,
        clock,
        actor="user",
        action="claim_approved",
        payload={"claim_id": claim_id},
    )
    return send_claim(conn, claim_id=claim_id, clock=clock)


def reject_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: int,
    clock: Clock,
) -> dict[str, Any]:
    claim = _get_claim(conn, claim_id)
    if claim is None:
        raise KeyError(f"claim {claim_id} not found")
    if claim["status"] != "draft":
        raise ValueError(f"cannot reject claim in status {claim['status']}")
    conn.execute(
        "UPDATE claims SET status = 'rejected' WHERE id = ?",
        (claim_id,),
    )
    log_action(
        conn,
        clock,
        actor="user",
        action="claim_rejected",
        payload={"claim_id": claim_id},
    )
    return {"claim_id": claim_id, "status": "rejected"}


def send_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: int,
    clock: Clock,
) -> dict[str, Any]:
    claim = _get_claim(conn, claim_id)
    if claim is None:
        raise KeyError(f"claim {claim_id} not found")
    if claim["status"] != "approved" or not claim["approved_at"]:
        raise ApprovalRequired(claim_id)

    purchase = conn.execute(
        "SELECT merchant, item, amount_cents FROM purchases WHERE id = ?",
        (claim["purchase_id"],),
    ).fetchone()
    if purchase is None:
        raise KeyError(f"purchase {claim['purchase_id']} not found")

    to_address = f"returns@{_slug(purchase['merchant'])}.example"
    subject = f"Return request: {purchase['item']}"
    body = claim["draft_text"]
    queued_at = clock.now().isoformat()

    conn.execute(
        """
        INSERT INTO outbox (claim_id, to_address, subject, body, status, queued_at)
        VALUES (?, ?, ?, ?, 'queued', ?)
        """,
        (claim_id, to_address, subject, body, queued_at),
    )
    conn.execute(
        "UPDATE claims SET status = 'sent' WHERE id = ?",
        (claim_id,),
    )
    conn.execute(
        "UPDATE purchases SET status = 'claimed' WHERE id = ?",
        (claim["purchase_id"],),
    )
    log_action(
        conn,
        clock,
        actor="claim_writer",
        action="claim_sent",
        payload={"claim_id": claim_id, "to_address": to_address},
    )
    return {
        "claim_id": claim_id,
        "status": "sent",
        "outbox": {
            "to_address": to_address,
            "subject": subject,
            "status": "queued",
        },
    }


def accept_refund(
    conn: sqlite3.Connection,
    *,
    merchant: str,
    clock: Clock,
    minutes_saved: int = MINUTES_SAVED_PER_CLAIM,
) -> dict[str, Any]:
    """Demo-only: mark the merchant's sent claim outbox as refund_accepted + savings."""
    row = conn.execute(
        """
        SELECT o.id AS outbox_id, o.claim_id, c.purchase_id, p.amount_cents, p.merchant
        FROM outbox o
        JOIN claims c ON c.id = o.claim_id
        JOIN purchases p ON p.id = c.purchase_id
        WHERE lower(p.merchant) = lower(?)
          AND o.status IN ('queued', 'delivered')
          AND c.status = 'sent'
        ORDER BY o.id DESC
        LIMIT 1
        """,
        (merchant,),
    ).fetchone()
    if row is None:
        raise KeyError(f"no sent claim outbox for merchant {merchant}")

    claim_id = int(row["claim_id"])
    amount_cents = int(row["amount_cents"])
    conn.execute(
        "UPDATE outbox SET status = 'refund_accepted' WHERE id = ?",
        (row["outbox_id"],),
    )
    conn.execute(
        """
        UPDATE claims
        SET status = 'refund_accepted', amount_recovered_cents = ?
        WHERE id = ?
        """,
        (amount_cents, claim_id),
    )
    conn.execute(
        "UPDATE purchases SET status = 'done' WHERE id = ?",
        (row["purchase_id"],),
    )
    record_savings(
        conn,
        clock,
        kind="refund",
        merchant=row["merchant"],
        amount_cents=amount_cents,
        time_saved_min=minutes_saved,
        source_id=f"claim:{claim_id}",
    )
    log_action(
        conn,
        clock,
        actor="portal",
        action="refund_accepted",
        payload={"claim_id": claim_id, "merchant": merchant, "amount_cents": amount_cents},
    )
    return {
        "claim_id": claim_id,
        "status": "refund_accepted",
        "amount_cents": amount_cents,
    }


def _get_claim(conn: sqlite3.Connection, claim_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, purchase_id, draft_text, sources_json, status,
               approved_at, amount_recovered_cents
        FROM claims WHERE id = ?
        """,
        (claim_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _slug(merchant: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "" for ch in merchant) or "merchant"
