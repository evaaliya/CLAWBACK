"""Claim prepare / approve / reject endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.claim_writer import (
    ApprovalRequired,
    accept_refund,
    approve_claim,
    prepare_claim,
    reject_claim,
)
from app.db import connect
from app.events import get_broker
from app.llm import resolve_model_ids

router = APIRouter(tags=["claims"])


def _publish(event: str, data: dict | None = None) -> None:
    get_broker().publish(event, data or {})



class PrepareBody(BaseModel):
    purchase_id: int = Field(..., ge=1)


@router.post("/claims/prepare")
def post_prepare_claim(body: PrepareBody, request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    llm = request.app.state.llm
    search = request.app.state.search
    models = resolve_model_ids(settings)

    conn = connect(settings.database_file())
    try:
        result = prepare_claim(
            conn,
            purchase_id=body.purchase_id,
            search=search,
            llm=llm,
            clock=clock,
            jurisdiction=settings.policy_jurisdiction,
            model_ultra=models["ultra"],
            model_super=models["super"],
        )
        conn.commit()
        _publish("claim.changed", {"claim_id": result.get("claim_id")})
    finally:
        conn.close()
    return result


@router.post("/claims/{claim_id}/approve")
def post_approve_claim(claim_id: int, request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        try:
            result = approve_claim(conn, claim_id=claim_id, clock=clock)
            # Recorded / demo: simulate merchant refund without a live timer
            # (mock-portal.md — POST refund/accept or recorded-mode timer).
            if settings.recorded_mode:
                purchase = conn.execute(
                    """
                    SELECT p.merchant FROM claims c
                    JOIN purchases p ON p.id = c.purchase_id
                    WHERE c.id = ?
                    """,
                    (claim_id,),
                ).fetchone()
                if purchase is not None:
                    refunded = accept_refund(
                        conn,
                        merchant=purchase["merchant"],
                        clock=clock,
                        minutes_saved=settings.minutes_saved_per_claim,
                    )
                    result["refund"] = refunded
                    _publish("savings.changed", {})
            conn.commit()
            _publish("claim.changed", {"claim_id": claim_id})
        except ApprovalRequired as exc:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "approval_required", "message": str(exc)}},
            ) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "invalid_state", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()
    return result


@router.post("/claims/{claim_id}/reject")
def post_reject_claim(claim_id: int, request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        try:
            result = reject_claim(conn, claim_id=claim_id, clock=clock)
            conn.commit()
            _publish("claim.changed", {"claim_id": claim_id})
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "invalid_state", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()
    return result
