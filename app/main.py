"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.claims import router as claims_router
from app.api.deadlines import router as deadlines_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.jobs import router as jobs_router
from app.api.subscriptions import router as subscriptions_router
from app.clock import clock_from_settings
from app.config import get_settings
from app.db import connect, init_db
from app.llm import build_llm
from app.portal.routes import router as portal_router
from app.search import build_search


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.clock = clock_from_settings(settings.demo_today)
    app.state.llm = build_llm(settings)
    app.state.search = build_search(settings)
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
app.include_router(deadlines_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(claims_router, prefix="/api")
app.include_router(portal_router)
