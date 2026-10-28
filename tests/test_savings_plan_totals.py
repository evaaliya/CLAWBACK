"""T17 — Seeded plan sums to 84700 cents and 360 minutes; source_id unique."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.clock import Clock
from app.savings import record_savings
from app.savings.query import savings_summary


def test_savings_plan_totals(demo_dir: Path, seeded_conn) -> None:
    plan = json.loads((demo_dir / "savings_plan.json").read_text(encoding="utf-8"))
    assert plan["expected_total_cents"] == 84_700
    assert plan["expected_time_saved_min"] == 360

    events = plan["events"]
    assert sum(int(e["amount_cents"]) for e in events) == 84_700
    assert sum(int(e["time_saved_min"]) for e in events) == 360

    seeded = seeded_conn.execute(
        """
        SELECT SUM(amount_cents) AS cents, SUM(time_saved_min) AS minutes
        FROM savings_events
        """
    ).fetchone()
    assert seeded["cents"] == 9_600
    assert seeded["minutes"] == 60

    summary = savings_summary(seeded_conn)
    assert summary["amount_cents"] == 9_600
    assert summary["time_saved_min"] == 60
    assert any(e["source_id"] == "dailynews-cancel" for e in summary["events"])


def test_savings_event_unique(conn, clock: Clock) -> None:
    record_savings(
        conn,
        clock,
        kind="cancel",
        merchant="DailyNews",
        amount_cents=9_600,
        time_saved_min=60,
        source_id="dailynews-cancel",
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        record_savings(
            conn,
            clock,
            kind="cancel",
            merchant="DailyNews",
            amount_cents=9_600,
            time_saved_min=60,
            source_id="dailynews-cancel",
        )
