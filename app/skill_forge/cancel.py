"""Start / confirm subscription cancellation (skill replay or Ultra path)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Protocol

from app.agent_log import log_action
from app.clock import Clock
from app.portal.actions import get_status, record_cancel_approval
from app.rules import MINUTES_SAVED_PER_CANCEL
from app.savings import record_savings
from app.skill_forge.errors import SkillReplayError
from app.skill_forge.plan import execute_portal_steps, plan_cancel_steps
from app.skill_forge.tools import find_skill, run_skill, save_skill


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


def start_cancel(
    conn: sqlite3.Connection,
    *,
    subscription_id: int,
    llm: LLMClient,
    clock: Clock,
    model_ultra: str,
) -> dict[str, Any]:
    sub = _get_subscription(conn, subscription_id)
    merchant = sub["merchant"]
    skill = find_skill(conn, merchant=merchant, intent="cancel subscription")

    if skill is not None:
        _store_pending(
            conn,
            clock,
            subscription_id=subscription_id,
            merchant=merchant,
            path="skill",
            steps=skill["steps"],
            skill_id=int(skill["id"]),
        )
        log_action(
            conn,
            clock,
            actor="skill_forge",
            action="start_cancel",
            payload={
                "subscription_id": subscription_id,
                "merchant": merchant,
                "path": "skill",
                "skill_id": skill["id"],
            },
        )
        return {
            "subscription_id": subscription_id,
            "merchant": merchant,
            "path": "skill",
            "status": "awaiting_confirmation",
            "skill_id": skill["id"],
            "steps": skill["steps"],
            "card": {
                "type": "cancel_plan",
                "merchant": merchant,
                "path": "skill",
                "skill_id": skill["id"],
                "steps": skill["steps"],
                "actions": ["Confirm"],
            },
        }

    steps = plan_cancel_steps(
        conn, clock, llm, merchant=merchant, model=model_ultra
    )
    _store_pending(
        conn,
        clock,
        subscription_id=subscription_id,
        merchant=merchant,
        path="ultra",
        steps=steps,
        skill_id=None,
    )
    log_action(
        conn,
        clock,
        actor="skill_forge",
        action="start_cancel",
        payload={
            "subscription_id": subscription_id,
            "merchant": merchant,
            "path": "ultra",
            "step_count": len(steps),
        },
    )
    return {
        "subscription_id": subscription_id,
        "merchant": merchant,
        "path": "ultra",
        "status": "awaiting_confirmation",
        "steps": steps,
        "card": {
            "type": "cancel_plan",
            "merchant": merchant,
            "path": "ultra",
            "steps": steps,
            "actions": ["Confirm"],
        },
    }


def confirm_cancel(
    conn: sqlite3.Connection,
    *,
    subscription_id: int,
    llm: LLMClient,
    clock: Clock,
    model_ultra: str,
    minutes_saved: int = MINUTES_SAVED_PER_CANCEL,
) -> dict[str, Any]:
    sub = _get_subscription(conn, subscription_id)
    if sub["status"] == "cancelled":
        raise ValueError(f"subscription {subscription_id} already cancelled")

    merchant = sub["merchant"]
    portal_template = sub["portal_template"] or "settings-menu"
    record_cancel_approval(
        conn, clock, merchant=merchant, subscription_id=subscription_id
    )

    pending = _load_pending(conn, subscription_id=subscription_id)
    skill = find_skill(conn, merchant=merchant, intent="cancel subscription")
    path = "skill"
    performed: list[dict[str, Any]] = []
    skill_id: int | None = int(skill["id"]) if skill else None
    source = f"mock-portal://{portal_template}/help/cancel"

    if skill is not None:
        try:
            result = run_skill(
                conn,
                clock,
                skill_id=int(skill["id"]),
                context={"merchant": merchant},
            )
            performed = result["performed_steps"]
        except SkillReplayError:
            path = "ultra_fallback"
            _abandon_partial_progress(conn, clock, merchant=merchant)
            steps = plan_cancel_steps(
                conn, clock, llm, merchant=merchant, model=model_ultra
            )
            performed = execute_portal_steps(
                conn, clock, merchant=merchant, steps=steps
            )
            saved = save_skill(
                conn,
                clock,
                merchant=merchant,
                portal_template=portal_template,
                steps=[
                    {"action": s["action"], "note": s.get("note", "")}
                    for s in performed
                ],
                sources=[source],
            )
            skill_id = int(saved["skill_id"])
    else:
        path = "ultra"
        steps = (pending or {}).get("steps") or plan_cancel_steps(
            conn, clock, llm, merchant=merchant, model=model_ultra
        )
        performed = execute_portal_steps(
            conn, clock, merchant=merchant, steps=steps
        )
        saved = save_skill(
            conn,
            clock,
            merchant=merchant,
            portal_template=portal_template,
            steps=[
                {"action": s["action"], "note": s.get("note", "")} for s in performed
            ],
            sources=[source],
        )
        skill_id = int(saved["skill_id"])

    status = get_status(conn, merchant)
    if status["status"] != "cancelled":
        raise RuntimeError(f"portal did not cancel {merchant}")

    conn.execute(
        "UPDATE subscriptions SET status = 'cancelled' WHERE id = ?",
        (subscription_id,),
    )
    amount_cents = int(sub["amount_monthly_cents"]) * 12
    record_savings(
        conn,
        clock,
        kind="cancel",
        merchant=merchant,
        amount_cents=amount_cents,
        time_saved_min=minutes_saved,
        source_id=f"cancel:sub:{subscription_id}",
    )
    log_action(
        conn,
        clock,
        actor="skill_forge",
        action="cancel_complete",
        payload={
            "subscription_id": subscription_id,
            "merchant": merchant,
            "path": path,
            "skill_id": skill_id,
            "amount_cents": amount_cents,
        },
    )
    return {
        "subscription_id": subscription_id,
        "merchant": merchant,
        "status": "cancelled",
        "path": path,
        "skill_id": skill_id,
        "confirmation_no": status["confirmation_no"],
        "performed_steps": performed,
        "amount_cents": amount_cents,
        "card": {
            "type": (
                "skill_learned" if path in ("ultra", "ultra_fallback") else "cancel_done"
            ),
            "merchant": merchant,
            "path": path,
            "skill_id": skill_id,
        },
    }


def _get_subscription(conn: sqlite3.Connection, subscription_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, merchant, merchant_norm, amount_monthly_cents, currency,
               portal_template, status
        FROM subscriptions WHERE id = ?
        """,
        (subscription_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"subscription {subscription_id} not found")
    return dict(row)


def _store_pending(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    subscription_id: int,
    merchant: str,
    path: str,
    steps: list[dict[str, Any]],
    skill_id: int | None,
) -> None:
    log_action(
        conn,
        clock,
        actor="skill_forge",
        action="cancel_pending",
        payload={
            "subscription_id": subscription_id,
            "merchant": merchant,
            "path": path,
            "steps": steps,
            "skill_id": skill_id,
        },
    )


def _load_pending(
    conn: sqlite3.Connection, *, subscription_id: int
) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT payload_json FROM agent_log
        WHERE action = 'cancel_pending'
        ORDER BY id DESC
        """
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        if int(payload.get("subscription_id", -1)) == subscription_id:
            return payload
    return None


def _abandon_partial_progress(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    merchant: str,
) -> None:
    """Clear mid-flow portal progress so a fallback plan can start from step 0."""
    log_action(
        conn,
        clock,
        actor="portal",
        action="portal_step",
        payload={
            "merchant": merchant,
            "action": "__abandon__",
            "ok": False,
            "status": "active",
        },
    )
