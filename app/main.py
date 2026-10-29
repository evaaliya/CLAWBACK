"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.activity import router as activity_router
from app.api.chat import router as chat_router
from app.api.claims import router as claims_router
from app.api.deadlines import router as deadlines_router
from app.api.demo import router as demo_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.jobs import router as jobs_router
from app.api.savings import router as savings_router
from app.api.skills import router as skills_router
from app.api.subscriptions import router as subscriptions_router
from app.clock import clock_from_settings
from app.config import get_settings
from app.db import connect, init_db
from app.events import get_broker
from app.hardening.budget import LiveBudget
from app.hardening.rate_limit import RateLimiter
from app.llm import build_llm
from app.portal.routes import router as portal_router
from app.search import build_search

UI_DIR = Path(__file__).resolve().parent / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    clock = clock_from_settings(settings.demo_today)
    budget = LiveBudget(
        limit=settings.live_llm_daily_limit,
        path=settings.budget_state_path(),
        clock=clock,
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.budget = budget
    app.state.rate_limiter = RateLimiter()
    app.state.llm = build_llm(settings, budget=budget)
    app.state.search = build_search(settings, budget=budget)
    app.state.events = get_broker()
    conn = connect(settings.database_file())
    try:
        init_db(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Clawback", version="0.0.1", lifespan=lifespan)
app.include_router(health_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(subscriptions_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(deadlines_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(claims_router, prefix="/api")
app.include_router(savings_router, prefix="/api")
app.include_router(activity_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(demo_router, prefix="/api")
app.include_router(portal_router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
