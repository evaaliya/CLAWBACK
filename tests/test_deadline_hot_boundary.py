"""T5 — Replit subscription is hot with 3 days left; 8 days is not hot."""

from __future__ import annotations

from datetime import date, timedelta

from app.clock import Clock
from app.deadline_watcher import days_left, is_hot, scan
from app.rules import HOT_DEADLINE_DAYS


def _insert_purchase(
    conn,
    *,
    merchant: str,
    item: str,
    amount_cents: int,
    return_deadline: str,
    purchase_date: str = "2026-09-30",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES (?, ?, ?, ?, 'USD', ?, 'open')
        """,
        (merchant, item, purchase_date, amount_cents, return_deadline),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_deadline_hot_boundary(conn, clock: Clock) -> None:
    today = clock.today()
    assert today == date(2026, 10, 27)
    assert HOT_DEADLINE_DAYS == 7

    hot_deadline = (today + timedelta(days=3)).isoformat()  # 2026-10-30
    not_hot_deadline = (today + timedelta(days=8)).isoformat()
    boundary_hot = (today + timedelta(days=HOT_DEADLINE_DAYS)).isoformat()

    replit_id = _insert_purchase(
        conn,
        merchant="Replit",
        item="Core yearly subscription",
        amount_cents=23500,
        return_deadline=hot_deadline,
    )
    far_id = _insert_purchase(
        conn,
        merchant="OtherStore",
        item="Something else",
        amount_cents=5000,
        return_deadline=not_hot_deadline,
    )
    boundary_id = _insert_purchase(
        conn,
        merchant="BoundaryStore",
        item="Boundary item",
        amount_cents=1000,
        return_deadline=boundary_hot,
    )

    assert days_left(date.fromisoformat(hot_deadline), today) == 3
    assert days_left(date.fromisoformat(not_hot_deadline), today) == 8
    assert days_left(date.fromisoformat(boundary_hot), today) == HOT_DEADLINE_DAYS

    assert is_hot(3) is True
    assert is_hot(8) is False
    assert is_hot(HOT_DEADLINE_DAYS) is True
    assert is_hot(HOT_DEADLINE_DAYS + 1) is False
    assert is_hot(0) is True
    assert is_hot(-1) is False

    result = scan(conn, clock)
    conn.commit()

    notified = {n["purchase_id"] for n in result["notifications"]}
    assert replit_id in notified
    assert boundary_id in notified
    assert far_id not in notified

    replit_card = next(
        n for n in result["notifications"] if n["purchase_id"] == replit_id
    )
    assert replit_card["days_left"] == 3
    assert replit_card["payload"]["type"] == "deadline_alert"
    assert "Prepare claim" in replit_card["payload"]["actions"]

    rows = conn.execute(
        "SELECT purchase_id, kind FROM notifications ORDER BY purchase_id"
    ).fetchall()
    notified_ids = {r["purchase_id"] for r in rows}
    assert replit_id in notified_ids
    assert boundary_id in notified_ids
    assert far_id not in notified_ids
