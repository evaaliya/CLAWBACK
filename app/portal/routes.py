"""Mock merchant portal HTTP routes + refund-accept outbox action."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.claim_writer import accept_refund
from app.db import connect
from app.portal.actions import (
    get_account_view,
    get_help_cancel,
    get_status,
    perform_action,
)
from app.portal.errors import ActionUnavailable, ApprovalRequired

router = APIRouter(tags=["portal"])


@router.get("/portal/{merchant}/account")
def portal_account(merchant: str, request: Request) -> dict:
    settings = request.app.state.settings
    conn = connect(settings.database_file())
    try:
        try:
            return get_account_view(conn, merchant)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()


@router.get("/portal/{merchant}/help/cancel")
def portal_help_cancel(merchant: str, request: Request) -> dict:
    settings = request.app.state.settings
    conn = connect(settings.database_file())
    try:
        try:
            return get_help_cancel(conn, merchant)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()


@router.get("/portal/{merchant}/status")
def portal_status(merchant: str, request: Request) -> dict:
    settings = request.app.state.settings
    conn = connect(settings.database_file())
    try:
        try:
            return get_status(conn, merchant)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()


@router.post("/portal/{merchant}/actions/{action}")
def portal_action(merchant: str, action: str, request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        try:
            result = perform_action(conn, clock, merchant=merchant, action=action)
            conn.commit()
            return result
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
        except ApprovalRequired as exc:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "approval_required",
                        "message": str(exc),
                        "merchant": exc.merchant,
                    }
                },
            ) from exc
        except ActionUnavailable as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "action_unavailable",
                        "message": str(exc),
                        "action": exc.action,
                    }
                },
            ) from exc
    finally:
        conn.close()


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
