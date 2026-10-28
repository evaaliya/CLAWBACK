"""GET /api/health — liveness, database check, recorded_mode flag."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import check_db, connect

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    db_ok = False
    try:
        conn = connect(settings.database_file())
        try:
            db_ok = check_db(conn)
        finally:
            conn.close()
    except OSError:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "recorded_mode": bool(settings.recorded_mode),
    }
