"""T6 — Scan twice → one card per day."""

from __future__ import annotations

from datetime import timedelta

from app.clock import Clock
from app.deadline_watcher import scan


def test_scan_idempotent(conn, clock: Clock) -> None:
    today = clock.today()
    deadline = (today + timedelta(days=3)).isoformat()

    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('SoundHub', 'Headphones', '2026-09-30', 23500, 'USD', ?, 'open')
        """,
        (deadline,),
    )
    purchase_id = int(cur.lastrowid)
    conn.commit()

    first = scan(conn, clock)
    conn.commit()
    second = scan(conn, clock)
    conn.commit()

    assert first["created"] == 1
    assert second["created"] == 0
    assert len(first["notifications"]) == 1
    assert second["notifications"] == []

    count = conn.execute(
        """
        SELECT COUNT(*) AS n FROM notifications
        WHERE kind = 'deadline_alert' AND purchase_id = ? AND day = ?
        """,
        (purchase_id, today.isoformat()),
    ).fetchone()["n"]
    assert count == 1

    total = conn.execute("SELECT COUNT(*) AS n FROM notifications").fetchone()["n"]
    assert total == 1
