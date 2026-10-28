"""GET /events — Server-Sent Events stream."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.events.hub import get_broker, sse_format

router = APIRouter(tags=["events"])


@router.get("/events")
async def get_events(request: Request) -> StreamingResponse:
    broker = getattr(request.app.state, "events", None) or get_broker()

    async def gen():
        yield sse_format("connected", {})
        queue_iter = broker.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(
                        queue_iter.__anext__(), timeout=15.0
                    )
                except asyncio.TimeoutError:
                    # Keep-alive comment so proxies do not close the stream.
                    yield ": keepalive\n\n"
                    continue
                except StopAsyncIteration:
                    break
                yield sse_format(event, data)
        finally:
            await queue_iter.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
