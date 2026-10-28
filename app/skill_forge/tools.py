"""find_skill, run_skill, save_skill tools."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.agent_log import log_action
from app.clock import Clock
from app.portal.actions import get_status, perform_action
from app.portal.errors import ActionUnavailable, ApprovalRequired
from app.skill_forge.errors import SkillReplayError


def find_skill(
    conn: sqlite3.Connection,
    *,
    merchant: str,
    intent: str = "cancel subscription",
) -> dict[str, Any] | None:
    """Lookup: merchant + trigger, then portal_template + trigger."""
    intent_norm = intent.strip().lower()
    row = conn.execute(
        """
        SELECT id, name, merchant, portal_template, trigger, steps_json,
               sources_json, success_count, learned_at, last_used_at
        FROM skills
        WHERE lower(merchant) = lower(?) AND lower(trigger) = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (merchant, intent_norm),
    ).fetchone()
    if row is None:
        template = conn.execute(
            """
            SELECT portal_template FROM portal_accounts
            WHERE lower(merchant) = lower(?)
            """,
            (merchant,),
        ).fetchone()
        if template is None:
            template = conn.execute(
                """
                SELECT portal_template FROM subscriptions
                WHERE lower(merchant) = lower(?)
                LIMIT 1
                """,
                (merchant,),
            ).fetchone()
        if template and template["portal_template"]:
            row = conn.execute(
                """
                SELECT id, name, merchant, portal_template, trigger, steps_json,
                       sources_json, success_count, learned_at, last_used_at
                FROM skills
                WHERE portal_template = ? AND lower(trigger) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (template["portal_template"], intent_norm),
            ).fetchone()

    if row is None:
        return None
    return _row_to_skill(row)


def run_skill(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    skill_id: int,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Replay skill steps against the portal. No Ultra call."""
    row = conn.execute(
        """
        SELECT id, name, merchant, portal_template, trigger, steps_json,
               sources_json, success_count, learned_at, last_used_at
        FROM skills WHERE id = ?
        """,
        (skill_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"skill {skill_id} not found")
    skill = _row_to_skill(row)
    merchant = str(context.get("merchant") or skill["merchant"])
    steps = skill["steps"]
    performed: list[dict[str, Any]] = []

    log_action(
        conn,
        clock,
        actor="skill_forge",
        action="run_skill",
        payload={"skill_id": skill_id, "merchant": merchant, "step_count": len(steps)},
    )

    for step in steps:
        action = step["action"]
        try:
            result = perform_action(conn, clock, merchant=merchant, action=action)
        except ApprovalRequired:
            raise
        except ActionUnavailable as exc:
            raise SkillReplayError(
                skill_id=skill_id,
                action=action,
                reason=exc.reason or str(exc),
            ) from exc
        performed.append({"action": action, "note": step.get("note", ""), "result": result})

    status = get_status(conn, merchant)
    if status["status"] != "cancelled":
        raise SkillReplayError(
            skill_id=skill_id,
            action="verify",
            reason=f"portal status is {status['status']!r}, expected cancelled",
        )

    conn.execute(
        "UPDATE skills SET last_used_at = ?, success_count = success_count + 1 WHERE id = ?",
        (clock.today().isoformat(), skill_id),
    )
    return {
        "skill_id": skill_id,
        "merchant": merchant,
        "performed_steps": performed,
        "portal_status": status["status"],
        "confirmation_no": status["confirmation_no"],
    }


def save_skill(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    merchant: str,
    portal_template: str,
    steps: list[dict[str, Any]],
    sources: list[str],
    trigger: str = "cancel subscription",
    name: str | None = None,
) -> dict[str, Any]:
    """Save steps actually performed. Existing name → update steps + bump success."""
    skill_name = name or f"cancel_subscription:{portal_template}"
    steps_json = json.dumps(steps, ensure_ascii=False)
    sources_json = json.dumps(sources, ensure_ascii=False)
    existing = conn.execute(
        "SELECT id, success_count FROM skills WHERE name = ?",
        (skill_name,),
    ).fetchone()
    if existing is not None:
        skill_id = int(existing["id"])
        conn.execute(
            """
            UPDATE skills
            SET merchant = ?, portal_template = ?, trigger = ?,
                steps_json = ?, sources_json = ?,
                success_count = success_count + 1,
                last_used_at = ?
            WHERE id = ?
            """,
            (
                merchant,
                portal_template,
                trigger,
                steps_json,
                sources_json,
                clock.today().isoformat(),
                skill_id,
            ),
        )
        created = False
    else:
        today = clock.today().isoformat()
        cur = conn.execute(
            """
            INSERT INTO skills
                (name, merchant, portal_template, trigger, steps_json, sources_json,
                 success_count, learned_at, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                skill_name,
                merchant,
                portal_template,
                trigger,
                steps_json,
                sources_json,
                today,
                today,
            ),
        )
        skill_id = int(cur.lastrowid)
        created = True

    log_action(
        conn,
        clock,
        actor="skill_forge",
        action="save_skill",
        payload={
            "skill_id": skill_id,
            "name": skill_name,
            "merchant": merchant,
            "portal_template": portal_template,
            "created": created,
            "step_count": len(steps),
        },
    )
    return {
        "skill_id": skill_id,
        "name": skill_name,
        "merchant": merchant,
        "portal_template": portal_template,
        "created": created,
    }


def list_skills(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, name, merchant, portal_template, trigger, steps_json,
               sources_json, success_count, learned_at, last_used_at
        FROM skills
        ORDER BY id ASC
        """
    ).fetchall()
    return [_row_to_skill(row) for row in rows]


def _row_to_skill(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "merchant": row["merchant"],
        "portal_template": row["portal_template"],
        "trigger": row["trigger"],
        "steps": json.loads(row["steps_json"]),
        "sources": json.loads(row["sources_json"]),
        "success_count": int(row["success_count"]),
        "learned_at": row["learned_at"],
        "last_used_at": row["last_used_at"],
    }
