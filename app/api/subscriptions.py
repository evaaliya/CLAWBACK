"""GET /subscriptions and cancel / confirm endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.db import connect
from app.events import get_broker
from app.ingest.subscriptions import list_subscriptions
from app.portal.errors import ActionUnavailable, ApprovalRequired
from app.skill_forge import confirm_cancel, start_cancel

router = APIRouter(tags=["subscriptions"])


def _publish(event: str, data: dict | None = None) -> None:
    get_broker().publish(event, data or {})



@router.get("/subscriptions")
def get_subscriptions(request: Request) -> dict:
    settings = request.app.state.settings
    conn = connect(settings.database_file())
    try:
        subs = list_subscriptions(conn)
    finally:
        conn.close()
    return {"subscriptions": subs, "count": len(subs)}


@router.post("/subscriptions/{subscription_id}/cancel")
def post_cancel(subscription_id: int, request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    llm = request.app.state.llm
    conn = connect(settings.database_file())
    try:
        try:
            result = start_cancel(
                conn,
                subscription_id=subscription_id,
                llm=llm,
                clock=clock,
                model_ultra=settings.model_ultra,
            )
            conn.commit()
            _publish("subscription.changed", {"subscription_id": subscription_id})
            return result
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(exc)}},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "conflict", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()


@router.post("/subscriptions/{subscription_id}/cancel/confirm")
def post_cancel_confirm(subscription_id: int, request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    llm = request.app.state.llm
    conn = connect(settings.database_file())
    try:
        try:
            result = confirm_cancel(
                conn,
                subscription_id=subscription_id,
                llm=llm,
                clock=clock,
                model_ultra=settings.model_ultra,
                minutes_saved=settings.minutes_saved_per_cancel,
            )
            conn.commit()
            _publish("subscription.changed", {"subscription_id": subscription_id})
            _publish("savings.changed", {})
            if result.get("path") in ("ultra", "ultra_fallback"):
                _publish("skill.saved", {"skill_id": result.get("skill_id")})
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
                    }
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "conflict", "message": str(exc)}},
            ) from exc
    finally:
        conn.close()
