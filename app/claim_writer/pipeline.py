"""Claim prepare pipeline: search → Ultra draft → validate → save draft or error card."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any, Protocol

from app.agent_log import log_action
from app.claim_writer.draft import ClaimDraft, draft_claim, super_validate
from app.claim_writer.policy import web_search_policy
from app.claim_writer.validator import validate_draft
from app.clock import Clock


class SearchClient(Protocol):
    def search(self, query: str, **params: Any) -> list[dict[str, Any]]: ...


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


def prepare_claim(
    conn: sqlite3.Connection,
    *,
    purchase_id: int,
    search: SearchClient,
    llm: LLMClient,
    clock: Clock,
    jurisdiction: str = "",
    model_ultra: str = "ultra",
    model_super: str = "super",
) -> dict[str, Any]:
    purchase = _load_purchase(conn, purchase_id)
    if purchase is None:
        return _error_result("purchase_not_found", f"purchase {purchase_id} not found")

    # 1) Tavily policy search — never fall back to model memory.
    try:
        sources = web_search_policy(
            conn,
            clock,
            search,
            merchant=str(purchase["merchant"]),
            jurisdiction=jurisdiction,
        )
    except Exception as exc:  # noqa: BLE001 — surface as error card (T12)
        log_action(
            conn,
            clock,
            actor="claim_writer",
            action="prepare_claim_failed",
            payload={"purchase_id": purchase_id, "stage": "search", "error": type(exc).__name__},
        )
        return _error_result("search_failed", "Policy search failed; no draft created.")

    if not sources:
        return _error_result("search_empty", "No policy sources found; no draft created.")

    # 2) Ultra draft + 3) validate (retry once with feedback).
    feedback: str | None = None
    last_reasons: list[str] = []
    for attempt in range(2):
        recording_key = "claim:draft" if attempt == 0 else "claim:draft:retry"
        try:
            draft = draft_claim(
                conn,
                clock,
                llm,
                purchase=purchase,
                policy_sources=sources,
                model=model_ultra,
                recording_key=recording_key,
                feedback=feedback,
            )
        except Exception as exc:  # noqa: BLE001 — T12 model failure
            log_action(
                conn,
                clock,
                actor="claim_writer",
                action="prepare_claim_failed",
                payload={
                    "purchase_id": purchase_id,
                    "stage": "draft",
                    "error": type(exc).__name__,
                },
            )
            return _error_result("model_failed", "Model failed; no draft created.")

        reasons = validate_draft(
            draft=draft.model_dump(),
            purchase=purchase,
            session_sources=sources,
            as_of=clock.today(),
        )
        super_ok, super_reasons = super_validate(
            conn,
            clock,
            llm,
            draft=draft,
            purchase=purchase,
            model=model_super,
        )
        if not super_ok:
            reasons = reasons + [r for r in super_reasons if r not in reasons]

        if not reasons:
            return _save_draft(conn, clock, purchase=purchase, draft=draft, sources=sources)

        last_reasons = reasons
        feedback = "; ".join(reasons)

    log_action(
        conn,
        clock,
        actor="claim_writer",
        action="prepare_claim_rejected",
        payload={"purchase_id": purchase_id, "reasons": last_reasons},
    )
    return _error_result(
        "could_not_be_verified",
        "Claim could not be verified; nothing shown.",
        details=last_reasons,
    )


def _save_draft(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    purchase: dict[str, Any],
    draft: ClaimDraft,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    sources_json = json.dumps(sources, ensure_ascii=False)
    cur = conn.execute(
        """
        INSERT INTO claims (purchase_id, draft_text, sources_json, status)
        VALUES (?, ?, ?, 'draft')
        """,
        (purchase["id"], draft.text, sources_json),
    )
    claim_id = int(cur.lastrowid)
    deadline_days = _deadline_days(purchase, clock.today())
    card = {
        "type": "claim_draft",
        "claim_id": claim_id,
        "title": f"{purchase['merchant']} return",
        "body": draft.text,
        "sources": [
            {"title": s.get("title") or "", "url": s.get("url") or ""}
            for s in sources
            if s.get("url")
        ],
        "actions": ["approve", "reject", "edit"],
        "deadline_days": deadline_days,
    }
    log_action(
        conn,
        clock,
        actor="claim_writer",
        action="claim_draft_saved",
        payload={"claim_id": claim_id, "purchase_id": purchase["id"]},
    )
    return {"ok": True, "claim_id": claim_id, "card": card, "status": "draft"}


def _load_purchase(conn: sqlite3.Connection, purchase_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, merchant, item, date, amount_cents, currency,
               return_deadline, warranty_until, status
        FROM purchases WHERE id = ?
        """,
        (purchase_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _deadline_days(purchase: dict[str, Any], today: date) -> int | None:
    raw = purchase.get("return_deadline") or purchase.get("warranty_until")
    if not raw:
        return None
    return (date.fromisoformat(str(raw)) - today).days


def _error_result(
    code: str,
    message: str,
    *,
    details: list[str] | None = None,
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "type": "error",
        "title": "Claim not available",
        "body": message,
        "code": code,
        "actions": [],
    }
    if details:
        card["details"] = details
    return {"ok": False, "claim_id": None, "card": card, "error": {"code": code, "message": message}}
