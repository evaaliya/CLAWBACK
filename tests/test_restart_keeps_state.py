"""T22 — Restart keeps claims, skills and notifications."""

from __future__ import annotations

import json
from pathlib import Path

from app.clock import Clock
from app.db import connect, init_db
from app.deadline_watcher import scan
from app.seed import seed_all


def test_restart_keeps_state(db_path: Path, demo_dir: Path, clock: Clock) -> None:
    conn = connect(db_path)
    init_db(conn)
    seed_all(conn, demo_dir, clock)

    skill_before = conn.execute(
        "SELECT id, name, steps_json FROM skills ORDER BY id"
    ).fetchall()
    assert len(skill_before) >= 1

    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('Replit', 'Core yearly subscription',
                '2026-09-30', 23500, 'USD', '2026-10-30', 'open')
        """
    )
    purchase_id = int(cur.lastrowid)
    sources = [{"title": "Policy", "url": "https://example.com/returns"}]
    claim_cur = conn.execute(
        """
        INSERT INTO claims (purchase_id, draft_text, sources_json, status)
        VALUES (?, ?, ?, 'draft')
        """,
        (purchase_id, "Please refund my Core yearly subscription.", json.dumps(sources)),
    )
    claim_id = int(claim_cur.lastrowid)

    scan_result = scan(conn, clock, hot_deadline_days=7)
    conn.commit()
    assert scan_result["created"] >= 1

    notif_before = conn.execute(
        "SELECT id, kind, purchase_id, day, payload_json FROM notifications ORDER BY id"
    ).fetchall()
    assert len(notif_before) >= 1

    claim_row = conn.execute(
        "SELECT id, purchase_id, draft_text, status FROM claims WHERE id = ?",
        (claim_id,),
    ).fetchone()
    assert claim_row is not None

    conn.close()

    # "Restart": new connection to the same SQLite file.
    conn2 = connect(db_path)
    try:
        skills = conn2.execute(
            "SELECT id, name, steps_json FROM skills ORDER BY id"
        ).fetchall()
        assert [dict(r) for r in skills] == [dict(r) for r in skill_before]

        claim = conn2.execute(
            "SELECT id, purchase_id, draft_text, status FROM claims WHERE id = ?",
            (claim_id,),
        ).fetchone()
        assert claim is not None
        assert claim["status"] == "draft"
        assert claim["purchase_id"] == purchase_id
        assert "subscription" in claim["draft_text"].lower()

        notifs = conn2.execute(
            "SELECT id, kind, purchase_id, day, payload_json FROM notifications ORDER BY id"
        ).fetchall()
        assert [dict(r) for r in notifs] == [dict(r) for r in notif_before]
    finally:
        conn2.close()
