"""T14 — Saved skill cancels FitPulse with zero Ultra calls, under 5 seconds."""

from __future__ import annotations

import time

from app.clock import Clock
from app.llm.fake import FakeLLM
from app.skill_forge.cancel import confirm_cancel, start_cancel


def _fitpulse_id(conn) -> int:
    row = conn.execute(
        "SELECT id FROM subscriptions WHERE merchant = ?",
        ("FitPulse",),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def test_skill_reuse_no_ultra(seeded_conn, clock: Clock) -> None:
    conn = seeded_conn
    sub_id = _fitpulse_id(conn)
    llm = FakeLLM(default_response='{"steps":[]}')

    started = start_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()
    assert started["path"] == "skill"
    assert started["status"] == "awaiting_confirmation"

    t0 = time.perf_counter()
    result = confirm_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()
    elapsed = time.perf_counter() - t0

    assert result["status"] == "cancelled"
    assert result["path"] == "skill"
    assert llm.ultra_calls == 0
    assert elapsed < 5.0

    portal = conn.execute(
        "SELECT status, confirmation_no FROM portal_accounts WHERE merchant = ?",
        ("FitPulse",),
    ).fetchone()
    assert portal["status"] == "cancelled"
    assert portal["confirmation_no"]

    sub = conn.execute(
        "SELECT status FROM subscriptions WHERE id = ?", (sub_id,)
    ).fetchone()
    assert sub["status"] == "cancelled"

    event = conn.execute(
        """
        SELECT kind, amount_cents, time_saved_min FROM savings_events
        WHERE source_id = ?
        """,
        (f"cancel:sub:{sub_id}",),
    ).fetchone()
    assert event is not None
    assert event["kind"] == "cancel"
    assert event["amount_cents"] == 12_00 * 12
    assert event["time_saved_min"] == 60
