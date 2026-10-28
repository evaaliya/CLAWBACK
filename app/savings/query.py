"""Read savings counter from savings_events (single source of truth)."""

from __future__ import annotations

import sqlite3
from typing import Any


def savings_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Counter: SUM(amount_cents), SUM(time_saved_min), plus event rows."""
    totals = conn.execute(
        """
        SELECT
            COALESCE(SUM(amount_cents), 0) AS amount_cents,
            COALESCE(SUM(time_saved_min), 0) AS time_saved_min,
            COUNT(*) AS event_count
        FROM savings_events
        """
    ).fetchone()
    rows = conn.execute(
        """
        SELECT id, kind, merchant, amount_cents, time_saved_min, source_id, created_at
        FROM savings_events
        ORDER BY id ASC
        """
    ).fetchall()
    return {
        "amount_cents": int(totals["amount_cents"]),
        "time_saved_min": int(totals["time_saved_min"]),
        "event_count": int(totals["event_count"]),
        "events": [dict(r) for r in rows],
    }
