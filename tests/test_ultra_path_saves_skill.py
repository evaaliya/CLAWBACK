"""T15 — Ultra path for StreamFlix saves a settings-menu skill."""

from __future__ import annotations

import json

from app.clock import Clock
from app.llm.fake import FakeLLM
from app.skill_forge.cancel import confirm_cancel, start_cancel


STREAMFLIX_PLAN = {
    "steps": [
        {"action": "open_settings", "note": "Settings"},
        {"action": "open_subscription", "note": "Subscription"},
        {"action": "manage_plan", "note": "Manage plan"},
        {"action": "end_plan", "note": "End plan"},
        {"action": "confirm_cancel", "note": "Requires user confirmation"},
        {"action": "save_confirmation", "note": "Store confirmation in memory"},
    ]
}


def _streamflix_id(conn) -> int:
    row = conn.execute(
        "SELECT id FROM subscriptions WHERE merchant = ?",
        ("StreamFlix",),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def test_ultra_path_saves_skill(seeded_conn, clock: Clock) -> None:
    conn = seeded_conn
    sub_id = _streamflix_id(conn)
    llm = FakeLLM(
        recordings={
            "cancel:plan:StreamFlix": json.dumps(STREAMFLIX_PLAN),
        }
    )

    before = conn.execute(
        "SELECT COUNT(*) AS n FROM skills WHERE portal_template = ?",
        ("settings-menu",),
    ).fetchone()["n"]
    assert before == 0

    started = start_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()
    assert started["path"] == "ultra"
    assert started["status"] == "awaiting_confirmation"
    assert llm.ultra_calls == 1

    result = confirm_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()
    assert result["status"] == "cancelled"
    assert result["path"] == "ultra"

    skill = conn.execute(
        """
        SELECT name, merchant, portal_template, steps_json, success_count
        FROM skills WHERE portal_template = ?
        """,
        ("settings-menu",),
    ).fetchone()
    assert skill is not None
    assert skill["name"] == "cancel_subscription:settings-menu"
    assert skill["merchant"] == "StreamFlix"
    assert skill["portal_template"] == "settings-menu"
    assert skill["success_count"] >= 1
    steps = json.loads(skill["steps_json"])
    actions = [s["action"] for s in steps]
    assert "confirm_cancel" in actions
    assert "end_plan" in actions

    portal = conn.execute(
        "SELECT status FROM portal_accounts WHERE merchant = ?",
        ("StreamFlix",),
    ).fetchone()
    assert portal["status"] == "cancelled"
