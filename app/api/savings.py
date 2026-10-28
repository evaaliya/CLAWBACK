"""GET /savings — counter from savings_events."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import connect
from app.savings import savings_summary

router = APIRouter(tags=["savings"])


@router.get("/savings")
def get_savings(request: Request) -> dict:
    settings = request.app.state.settings
    conn = connect(settings.database_file())
    try:
        return savings_summary(conn)
    finally:
        conn.close()
