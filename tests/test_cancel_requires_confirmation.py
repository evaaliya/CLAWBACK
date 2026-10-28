"""T13 — Portal cancel requires confirm_cancel after approval."""

from __future__ import annotations

import pytest

from app.clock import Clock
from app.portal.actions import perform_action
from app.skill_forge.errors import ApprovalRequired
from app.skill_forge.tools import find_skill, run_skill


def test_cancel_requires_confirmation(seeded_conn, clock: Clock) -> None:
    conn = seeded_conn
    skill = find_skill(conn, merchant="FitPulse", intent="cancel subscription")
    assert skill is not None

    with pytest.raises(ApprovalRequired):
        run_skill(
            conn,
            clock,
            skill_id=int(skill["id"]),
            context={"merchant": "FitPulse"},
        )

    status = conn.execute(
        "SELECT status FROM portal_accounts WHERE merchant = ?",
        ("FitPulse",),
    ).fetchone()["status"]
    assert status == "active"

    with pytest.raises(ApprovalRequired):
        perform_action(conn, clock, merchant="FitPulse", action="confirm_cancel")

    status2 = conn.execute(
        "SELECT status FROM portal_accounts WHERE merchant = ?",
        ("FitPulse",),
    ).fetchone()["status"]
    assert status2 == "active"
