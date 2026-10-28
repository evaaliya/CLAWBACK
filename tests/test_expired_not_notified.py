"""T7 — Expired deadline: no card, purchase expired."""

from __future__ import annotations

from datetime import timedelta

from app.clock import Clock
from app.deadline_watcher import scan


def test_expired_not_notified(conn, clock: Clock) -> None:
    today = clock.today()
    expired_deadline = (today - timedelta(days=1)).isoformat()

    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('OldStore', 'Expired gadget', '2026-08-01', 9900, 'USD', ?, 'open')
        """,
        (expired_deadline,),
    )
    purchase_id = int(cur.lastrowid)
    conn.commit()

    result = scan(conn, clock)
    conn.commit()

    assert result["created"] == 0
    assert result["notifications"] == []
    assert purchase_id in result["expired"]

    row = conn.execute(
        "SELECT status FROM purchases WHERE id = ?",
        (purchase_id,),
    ).fetchone()
    assert row["status"] == "expired"

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE purchase_id = ?",
        (purchase_id,),
    ).fetchone()["n"]
    assert count == 0
