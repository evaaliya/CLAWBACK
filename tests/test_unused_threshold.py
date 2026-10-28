"""T2 — Unused flag at the boundary; unknown usage is not unused."""

from __future__ import annotations

from datetime import date, timedelta

from app.clock import Clock
from app.ingest.subscriptions import apply_unused_flag, days_since_used
from app.rules import UNUSED_DAYS


def test_unused_threshold(conn, clock: Clock) -> None:
    today = clock.today()
    assert today == date(2026, 10, 27)

    # Exactly UNUSED_DAYS ago → still active (strictly greater than threshold).
    boundary = (today - timedelta(days=UNUSED_DAYS)).isoformat()
    just_over = (today - timedelta(days=UNUSED_DAYS + 1)).isoformat()
    recent = (today - timedelta(days=3)).isoformat()

    conn.execute(
        """
        INSERT INTO subscriptions
            (merchant, merchant_norm, amount_monthly_cents, currency,
             started_at, last_used_at, portal_template, status)
        VALUES
            ('AtBoundary', 'AtBoundary', 1000, 'USD', '2026-01-01', ?, 'settings-menu', 'active'),
            ('JustOver', 'JustOver', 1000, 'USD', '2026-01-01', ?, 'settings-menu', 'active'),
            ('Recent', 'Recent', 1000, 'USD', '2026-01-01', ?, 'settings-menu', 'active'),
            ('Unknown', 'Unknown', 1000, 'USD', '2026-01-01', NULL, 'settings-menu', 'active'),
            ('AlreadyCancelled', 'AlreadyCancelled', 800, 'USD', '2026-01-01', ?,
             'account-membership', 'cancelled')
        """,
        (boundary, just_over, recent, just_over),
    )
    conn.commit()

    assert days_since_used(today, date.fromisoformat(boundary)) == UNUSED_DAYS
    assert days_since_used(today, date.fromisoformat(just_over)) == UNUSED_DAYS + 1

    apply_unused_flag(conn, clock)
    conn.commit()

    rows = {
        r["merchant_norm"]: r["status"]
        for r in conn.execute(
            "SELECT merchant_norm, status FROM subscriptions"
        ).fetchall()
    }
    assert rows["AtBoundary"] == "active"
    assert rows["JustOver"] == "flagged"
    assert rows["Recent"] == "active"
    assert rows["Unknown"] == "active"  # missing usage → never "unused"
    assert rows["AlreadyCancelled"] == "cancelled"
