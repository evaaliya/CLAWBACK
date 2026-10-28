"""Minimal portal routes for M3: simulate refund acceptance on the outbox."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.claim_writer import accept_refund
from app.db import connect

router = APIRouter(tags=["portal"])


@router.post("/portal/{merchant}/refund/accept")
def post_refund_accept(merchant: str, request: Request) -> dict:
    """Demo-only: move the merchant's queued claim outbox to refund_accepted."""
    settings = request.app.state.settings
    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        try:
            result = accept_refund(
                conn,
                merchant=merchant,
                clock=clock,
                minutes_saved=settings.minutes_saved_per_claim,
            )
            conn.commit()
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()
    return result
