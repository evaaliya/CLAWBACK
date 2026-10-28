"""POST /ingest/statement and POST /ingest/receipts."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile

from app.db import connect
from app.ingest.service import ingest_receipts, ingest_statement
from app.llm import resolve_model_ids

router = APIRouter(tags=["ingest"])


@router.post("/ingest/statement")
async def post_statement(
    request: Request,
    file: UploadFile | None = File(default=None),
) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    llm = request.app.state.llm
    models = resolve_model_ids(settings)

    if file is not None:
        content = await file.read()
        filename = file.filename
    else:
        content = await request.body()
        filename = None
        ctype = request.headers.get("content-type", "")
        if "json" in ctype:
            filename = "statement.json"
        else:
            filename = "statement.csv"

    usage_path = Path(settings.demo_dir) / "subscription_usage.json"
    conn = connect(settings.database_file())
    try:
        result = ingest_statement(
            conn,
            content,
            llm=llm,
            clock=clock,
            filename=filename,
            usage_path=usage_path if usage_path.exists() else None,
            model=models["nano"],
        )
        conn.commit()
    finally:
        conn.close()
    return result


@router.post("/ingest/receipts")
async def post_receipts(
    request: Request,
    files: list[UploadFile] = File(...),
) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    llm = request.app.state.llm
    models = resolve_model_ids(settings)

    items: list[dict] = []
    for upload in files:
        raw = await upload.read()
        text = raw.decode("utf-8", errors="replace")
        items.append(
            {
                "text": text,
                "filename": upload.filename,
                "recording_key": f"receipt:{upload.filename}" if upload.filename else None,
            }
        )

    conn = connect(settings.database_file())
    try:
        result = ingest_receipts(
            conn,
            items,
            llm=llm,
            clock=clock,
            model=models["nano"],
        )
        conn.commit()
    finally:
        conn.close()
    return result
