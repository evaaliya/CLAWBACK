"""T21 — Every tool call has an agent_log row."""

from __future__ import annotations

import json

from app.claim_writer import prepare_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.savings import record_savings
from app.search.fake import FakeSearch
from app.skill_forge.tools import find_skill, run_skill, save_skill


SOUNDHUB_SOURCES = [
    {
        "title": "SoundHub Returns and Refunds (fixture)",
        "url": "https://example.com/soundhub/returns",
        "excerpt": (
            "Unused or lightly used items can be returned within 30 days "
            "of purchase for a full refund."
        ),
    }
]

CLAIM_DRAFT = {
    "text": (
        "Please refund my Wireless over-ear headphones SH-700 purchased on "
        "2026-09-30 for 23500 cents (USD)."
    ),
    "citations": [
        {
            "title": "SoundHub Returns and Refunds (fixture)",
            "url": "https://example.com/soundhub/returns",
            "excerpt": "Unused or lightly used items can be returned within 30 days.",
        }
    ],
}


def _actions(conn) -> set[str]:
    rows = conn.execute("SELECT DISTINCT action FROM agent_log").fetchall()
    return {row["action"] for row in rows}


def test_agent_log_complete(seeded_conn, clock: Clock) -> None:
    conn = seeded_conn

    # SPEC tools: web_search_policy, draft_claim, find_skill, run_skill,
    # save_skill, record_savings — each must leave an agent_log row.
    find_skill(conn, merchant="FitPulse", intent="cancel subscription", clock=clock)

    skill = conn.execute(
        "SELECT id FROM skills WHERE portal_template = ?",
        ("account-membership",),
    ).fetchone()
    assert skill is not None
    # run_skill needs cancel approval before confirm_cancel; log happens at start.
    try:
        run_skill(
            conn,
            clock,
            skill_id=int(skill["id"]),
            context={"merchant": "FitPulse"},
        )
    except Exception:
        # Portal may refuse mid-flow without approval; the tool still logged.
        pass

    save_skill(
        conn,
        clock,
        merchant="TuneBox",
        portal_template="settings-menu",
        steps=[
            {"action": "open_settings", "note": "Settings"},
            {"action": "confirm_cancel", "note": "Confirm"},
            {"action": "save_confirmation", "note": "Done"},
        ],
        sources=["mock-portal://settings-menu/help/cancel"],
    )

    record_savings(
        conn,
        clock,
        kind="cancel",
        merchant="TuneBox",
        amount_cents=12_000,
        time_saved_min=60,
        source_id="cancel:sub:test-log",
    )

    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('SoundHub', 'Wireless over-ear headphones SH-700',
                '2026-09-30', 23500, 'USD', '2026-10-30', 'open')
        """
    )
    purchase_id = int(cur.lastrowid)
    llm = FakeLLM(
        recordings={
            "claim:draft": json.dumps(CLAIM_DRAFT),
            "claim:validate": json.dumps({"ok": True, "reasons": []}),
        }
    )
    search = FakeSearch(
        recordings={"SoundHub return refund policy US": SOUNDHUB_SOURCES}
    )
    prepare_claim(
        conn,
        purchase_id=purchase_id,
        search=search,
        llm=llm,
        clock=clock,
        jurisdiction="US",
        model_ultra="ultra",
        model_super="super",
    )
    conn.commit()

    actions = _actions(conn)
    required = {
        "web_search_policy",
        "draft_claim",
        "find_skill",
        "run_skill",
        "save_skill",
        "record_savings",
    }
    missing = required - actions
    assert not missing, f"missing agent_log actions: {sorted(missing)}"
