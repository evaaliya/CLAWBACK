"""GET /api/activity — agent_log timeline + model usage."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.activity import activity_summary
from app.config import get_settings
from app.db import connect

router = APIRouter(tags=["activity"])


@router.get("/activity")
def get_activity(request: Request) -> dict:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    conn = connect(settings.database_file())
    try:
        return activity_summary(conn)
    finally:
        conn.close()
