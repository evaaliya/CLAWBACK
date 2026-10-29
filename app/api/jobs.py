"""POST /jobs/scan — same scan() as the Serverless Job entrypoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import connect
from app.deadline_watcher import scan
from app.events import get_broker
from app.hardening.http import reject

router = APIRouter(tags=["jobs"])


@router.post("/jobs/scan")
def post_jobs_scan(request: Request) -> dict:
    settings = request.app.state.settings
    expected = (settings.job_token or "").strip()
    if expected:
        provided = request.headers.get("x-job-token", "")
        if provided != expected:
            reject(
                "job_token_required",
                "Valid X-Job-Token header is required for scan.",
                status=401,
            )

    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        result = scan(
            conn,
            clock,
            hot_deadline_days=settings.hot_deadline_days,
        )
        conn.commit()
        if result.get("created"):
            get_broker().publish(
                "notification.new",
                {"count": result["created"], "day": result.get("day")},
            )
    finally:
        conn.close()
    return result
