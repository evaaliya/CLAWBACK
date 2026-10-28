"""GET /skills."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import connect
from app.skill_forge import list_skills

router = APIRouter(tags=["skills"])


@router.get("/skills")
def get_skills(request: Request) -> dict:
    settings = request.app.state.settings
    conn = connect(settings.database_file())
    try:
        skills = list_skills(conn)
    finally:
        conn.close()
    return {"skills": skills, "count": len(skills)}
