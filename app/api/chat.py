"""POST /chat."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.chat import handle_chat
from app.db import connect

router = APIRouter(tags=["chat"])


class ChatBody(BaseModel):
    message: str = Field(default="")


@router.post("/chat")
def post_chat(body: ChatBody, request: Request) -> dict:
    settings = request.app.state.settings
    clock = request.app.state.clock
    conn = connect(settings.database_file())
    try:
        result = handle_chat(conn, clock, message=body.message)
        conn.commit()
        return result
    finally:
        conn.close()
