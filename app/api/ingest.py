"""POST /ingest/statement and POST /ingest/receipts."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.db import connect
from app.hardening.uploads import UploadRejected, validate_upload
from app.ingest.service import ingest_receipts, ingest_statement
from app.llm import resolve_model_ids

router = APIRouter(tags=["ingest"])


def _reject_upload(exc: UploadRejected) -> None:
    raise HTTPException(status_code=400, detail=exc.as_error())


@router.post("/ingest/statement")
async def post_statement(
    request: Request,
    file: UploadFile | None = File(default=None),
) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    llm = request.app.state.llm
    models = resolve_model_ids(settings)
    max_bytes = settings.upload_max_bytes

    if file is not None:
        content = await file.read()
        filename = file.filename
        try:
            validate_upload(
                content=content,
                filename=filename,
                content_type=file.content_type,
                max_bytes=max_bytes,
            )
        except UploadRejected as exc:
            _reject_upload(exc)
    else:
        content = await request.body()
        filename = None
        ctype = request.headers.get("content-type", "")
        if "json" in ctype:
            filename = "statement.json"
        else:
            filename = "statement.csv"
        try:
            validate_upload(
                content=content,
                filename=filename,
                content_type=ctype,
                max_bytes=max_bytes,
            )
        except UploadRejected as exc:
            _reject_upload(exc)

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
    max_bytes = settings.upload_max_bytes

    items: list[dict] = []
    for upload in files:
        raw = await upload.read()
        try:
            validate_upload(
                content=raw,
                filename=upload.filename,
                content_type=upload.content_type,
                max_bytes=max_bytes,
            )
        except UploadRejected as exc:
            _reject_upload(exc)
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
