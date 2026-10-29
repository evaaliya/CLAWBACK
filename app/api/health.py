"""GET /api/health — liveness, database check, recorded_mode / budget badge."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import check_db, connect

router = APIRouter(tags=["health"])


def _badge(request: Request) -> str | None:
    settings = request.app.state.settings
    if settings.recorded_mode:
        return "recorded"
    budget = getattr(request.app.state, "budget", None)
    if budget is not None and budget.exhausted:
        return "recorded (live budget used)"
    return None


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

    badge = _badge(request)
    budget = getattr(request.app.state, "budget", None)
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "recorded_mode": bool(settings.recorded_mode) or bool(badge and "budget" in badge),
        "live_budget_exhausted": bool(budget.exhausted) if budget is not None else False,
        "badge": badge,
    }
