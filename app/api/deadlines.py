"""GET /deadlines."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import connect
from app.deadline_watcher import list_deadlines

router = APIRouter(tags=["deadlines"])


@router.get("/deadlines")
def get_deadlines(request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        deadlines = list_deadlines(
            conn,
            clock,
            hot_deadline_days=settings.hot_deadline_days,
        )
    finally:
        conn.close()
    return {"deadlines": deadlines, "count": len(deadlines)}
