"""Write rows to agent_log. Payloads hold ids and field names, never raw receipts.

`log_action` is the single wrapper every tool / decision must call (T21).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any, TypeVar

from app.clock import Clock

T = TypeVar("T")


def log_action(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    actor: str,
    action: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO agent_log (ts, actor, action, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            clock.now().isoformat(),
            actor,
            action,
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def with_log(
    conn: sqlite3.Connection,
    clock: Clock,
    *,
    actor: str,
    action: str,
    payload: dict[str, Any],
    fn: Callable[[], T],
) -> T:
    """Run a tool body and always record an agent_log row for the call."""
    result = fn()
    out_payload = dict(payload)
    if isinstance(result, dict) and "id" in result:
        out_payload.setdefault("result_id", result["id"])
    log_action(conn, clock, actor=actor, action=action, payload=out_payload)
    return result

