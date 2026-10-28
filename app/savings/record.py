"""record_savings tool — insert a savings_events row (source_id unique)."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.agent_log import log_action
from app.clock import Clock


def record_savings(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    kind: str,
    merchant: str,
    amount_cents: int,
    time_saved_min: int,
    source_id: str,
) -> dict[str, Any]:
    if kind not in ("cancel", "refund"):
        raise ValueError(f"invalid savings kind: {kind}")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
        raise TypeError("amount_cents must be int")
    cur = conn.execute(
        """
        INSERT INTO savings_events
            (kind, merchant, amount_cents, time_saved_min, source_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            kind,
            merchant,
            amount_cents,
            time_saved_min,
            source_id,
            clock.now().isoformat(),
        ),
    )
    log_action(
        conn,
        clock,
        actor="savings",
        action="record_savings",
        payload={
            "kind": kind,
            "merchant": merchant,
            "amount_cents": amount_cents,
            "time_saved_min": time_saved_min,
            "source_id": source_id,
            "id": cur.lastrowid,
        },
    )
    return {
        "id": int(cur.lastrowid),
        "kind": kind,
        "merchant": merchant,
        "amount_cents": amount_cents,
        "time_saved_min": time_saved_min,
        "source_id": source_id,
    }
