"""draft_claim tool — Ultra produces strict JSON {text, citations[]}."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agent_log import log_action
from app.clock import Clock


class Citation(BaseModel):
    title: str = ""
    url: str
    excerpt: str = ""


class ClaimDraft(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def text_nonempty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("text must be non-empty")
        return value


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


def draft_claim(
    conn: sqlite3.Connection,
    clock: Clock,
    llm: LLMClient,
    *,
    purchase: dict[str, Any],
    policy_sources: list[dict[str, Any]],
    model: str,
    recording_key: str = "claim:draft",
    feedback: str | None = None,
) -> ClaimDraft:
    prompt = _draft_prompt(purchase, policy_sources, feedback=feedback)
    raw = llm.complete(model=model, prompt=prompt, recording_key=recording_key)
    draft = ClaimDraft.model_validate(_as_dict(raw))
    log_action(
        conn,
        clock,
        actor="claim_writer",
        action="draft_claim",
        payload={
            "purchase_id": purchase.get("id"),
            "citation_count": len(draft.citations),
            "recording_key": recording_key,
            "had_feedback": feedback is not None,
        },
    )
    return draft


def super_validate(
    conn: sqlite3.Connection,
    clock: Clock,
    llm: LLMClient,
    *,
    draft: ClaimDraft,
    purchase: dict[str, Any],
    model: str,
    recording_key: str = "claim:validate",
) -> tuple[bool, list[str]]:
    """Ask Super for a structured ok/reasons check (advisory; code validator is law)."""
    prompt = (
        "Validate this refund claim draft. Reply JSON "
        '{"ok": true|false, "reasons": ["..."]}.\n'
        f"purchase={json.dumps(_purchase_facts(purchase), ensure_ascii=False)}\n"
        f"draft={draft.model_dump_json()}"
    )
    try:
        raw = llm.complete(model=model, prompt=prompt, recording_key=recording_key)
        data = _as_dict(raw)
        ok = bool(data.get("ok"))
        reasons = [str(r) for r in (data.get("reasons") or [])]
    except (ValidationError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        ok = False
        reasons = [f"super validate parse error: {exc}"]
    log_action(
        conn,
        clock,
        actor="claim_writer",
        action="validate_claim",
        payload={"ok": ok, "reason_count": len(reasons)},
    )
    return ok, reasons


def _draft_prompt(
    purchase: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    feedback: str | None,
) -> str:
    facts = _purchase_facts(purchase)
    base = (
        "Draft a refund claim as JSON only: "
        '{"text":"...","citations":[{"title":"...","url":"...","excerpt":"..."}]}.\n'
        "Use ONLY the purchase facts and the policy sources below. "
        "Every citation URL must come from the sources. "
        "Include item, date, and amount_cents in the text.\n"
        f"purchase={json.dumps(facts, ensure_ascii=False)}\n"
        f"sources={json.dumps(sources, ensure_ascii=False)}"
    )
    if feedback:
        return base + f"\nPrevious draft failed validation: {feedback}. Fix it."
    return base


def _purchase_facts(purchase: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": purchase.get("id"),
        "merchant": purchase.get("merchant"),
        "item": purchase.get("item"),
        "date": purchase.get("date"),
        "amount_cents": purchase.get("amount_cents"),
        "currency": purchase.get("currency"),
        "return_deadline": purchase.get("return_deadline"),
    }


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise TypeError(f"expected JSON object, got {type(raw)}")
