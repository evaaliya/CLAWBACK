"""Ultra planning path for cancellations when no skill exists (or replay failed)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agent_log import log_action
from app.clock import Clock
from app.portal.actions import get_help_cancel, perform_action
from app.portal.templates import default_steps_for_template
from app.portal.errors import ActionUnavailable, ApprovalRequired
from app.privacy.trace import complete_traced


class PlanStep(BaseModel):
    action: str
    note: str = ""

    @field_validator("action")
    @classmethod
    def action_nonempty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("action must be non-empty")
        return value.strip()


class CancelPlan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1)


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


def plan_cancel_steps(
    conn: sqlite3.Connection,
    clock: Clock,
    llm: LLMClient,
    *,
    merchant: str,
    model: str,
) -> list[dict[str, str]]:
    help_page = get_help_cancel(conn, merchant)
    prompt = (
        "Plan mock-portal cancellation steps as JSON only: "
        '{"steps":[{"action":"...","note":"..."}]}. '
        "Use only actions described in the help page. "
        "Include confirm_cancel and save_confirmation.\n"
        f"help={json.dumps(help_page, ensure_ascii=False)}"
    )
    recording_key = f"cancel:plan:{merchant}"
    raw = complete_traced(
        conn,
        clock,
        llm,
        role="plan",
        model=model,
        prompt=prompt,
        recording_key=recording_key,
    )
    try:
        plan = CancelPlan.model_validate(_as_dict(raw))
        steps = [{"action": s.action, "note": s.note} for s in plan.steps]
    except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
        # Deterministic fallback from the portal template (still counted as Ultra call).
        steps = default_steps_for_template(help_page["portal_template"])

    log_action(
        conn,
        clock,
        actor="skill_forge",
        action="plan_cancel",
        payload={
            "merchant": merchant,
            "step_count": len(steps),
            "recording_key": recording_key,
            "source": help_page.get("source"),
        },
    )
    return steps


def execute_portal_steps(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    merchant: str,
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run planned steps. Approval must already be stored for confirm_cancel."""
    performed: list[dict[str, Any]] = []
    for step in steps:
        action = step["action"]
        try:
            result = perform_action(conn, clock, merchant=merchant, action=action)
        except ApprovalRequired:
            raise
        except ActionUnavailable as exc:
            raise ActionUnavailable(
                merchant=merchant,
                action=action,
                reason=exc.reason or str(exc),
            ) from exc
        performed.append(
            {"action": action, "note": step.get("note", ""), "result": result}
        )
    return performed


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise TypeError(f"expected JSON object, got {type(raw)}")
