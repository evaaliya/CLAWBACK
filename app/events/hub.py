"""Simple asyncio pub/sub for GET /events (SSE)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator


class EventBroker:
    """Fan-out of named events to SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[tuple[str, dict[str, Any]]]] = []

    def publish(self, event: str, data: dict[str, Any] | None = None) -> None:
        payload = data or {}
        dead: list[asyncio.Queue[tuple[str, dict[str, Any]]]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait((event, payload))
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def subscribe(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=64)
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


_broker = EventBroker()


def get_broker() -> EventBroker:
    return _broker


def sse_format(event: str, data: dict[str, Any]) -> str:
    body = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n"
