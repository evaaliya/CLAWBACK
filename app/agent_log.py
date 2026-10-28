"""Write rows to agent_log. Payloads hold ids and field names, never raw receipts."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.clock import Clock


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
