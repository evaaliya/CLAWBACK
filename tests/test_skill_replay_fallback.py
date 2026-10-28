"""T16 — Failed replay falls back to Ultra and updates the skill."""

from __future__ import annotations

import json

from app.clock import Clock
from app.llm.fake import FakeLLM
from app.skill_forge.cancel import confirm_cancel, start_cancel


GOOD_ACCOUNT_STEPS = [
    {"action": "open_account_settings", "note": "Account > Membership"},
    {"action": "find_cancel_link", "note": "Cancel membership"},
    {"action": "confirm_cancel", "note": "Requires user confirmation"},
    {"action": "save_confirmation", "note": "Store confirmation in memory"},
]

BROKEN_STEPS = [
    {"action": "open_account_settings", "note": "Account > Membership"},
    {"action": "click_nonexistent_button", "note": "Broken step"},
    {"action": "confirm_cancel", "note": "Requires user confirmation"},
    {"action": "save_confirmation", "note": "Store confirmation in memory"},
]


def _fitpulse_id(conn) -> int:
    row = conn.execute(
        "SELECT id FROM subscriptions WHERE merchant = ?",
        ("FitPulse",),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def test_skill_replay_fallback(seeded_conn, clock: Clock) -> None:
    conn = seeded_conn
    sub_id = _fitpulse_id(conn)

    skill_before = conn.execute(
        "SELECT id, steps_json, success_count FROM skills WHERE portal_template = ?",
        ("account-membership",),
    ).fetchone()
    assert skill_before is not None
    skill_id = int(skill_before["id"])
    conn.execute(
        "UPDATE skills SET steps_json = ? WHERE id = ?",
        (json.dumps(BROKEN_STEPS), skill_id),
    )
    conn.commit()

    llm = FakeLLM(
        recordings={
            "cancel:plan:FitPulse": json.dumps({"steps": GOOD_ACCOUNT_STEPS}),
        }
    )

    started = start_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()
    assert started["path"] == "skill"

    result = confirm_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()

    assert result["status"] == "cancelled"
    assert result["path"] == "ultra_fallback"
    assert llm.ultra_calls >= 1

    skill_after = conn.execute(
        "SELECT steps_json, success_count FROM skills WHERE id = ?",
        (skill_id,),
    ).fetchone()
    steps = json.loads(skill_after["steps_json"])
    actions = [s["action"] for s in steps]
    assert "click_nonexistent_button" not in actions
    assert actions == [s["action"] for s in GOOD_ACCOUNT_STEPS]

    portal = conn.execute(
        "SELECT status FROM portal_accounts WHERE merchant = ?",
        ("FitPulse",),
    ).fetchone()
    assert portal["status"] == "cancelled"
