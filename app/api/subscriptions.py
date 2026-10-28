"""GET /subscriptions."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import connect
from app.ingest.subscriptions import list_subscriptions

router = APIRouter(tags=["subscriptions"])


@router.get("/subscriptions")
def get_subscriptions(request: Request) -> dict:
    settings = request.app.state.settings
    conn = connect(settings.database_file())
    try:
        subs = list_subscriptions(conn)
    finally:
        conn.close()
    return {"subscriptions": subs, "count": len(subs)}
