"""Read agent_log for the Activity tab and Models card."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def activity_summary(conn: sqlite3.Connection, *, limit: int = 200) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT id, ts, actor, action, payload_json
        FROM agent_log
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    events: list[dict[str, Any]] = []
    models: dict[str, dict[str, int]] = {}

    for row in reversed(rows):
        payload = _payload(row["payload_json"])
        action = row["action"]
        highlighted = _is_highlighted(action, payload)
        model = str(payload.get("model") or "")
        latency_ms = payload.get("latency_ms")
        status = _status(action, payload)
        events.append(
            {
                "id": row["id"],
                "ts": row["ts"],
                "actor": row["actor"],
                "action": action,
                "tool": action,
                "model": model or None,
                "latency_ms": latency_ms,
                "status": status,
                "highlighted": highlighted,
                "recorded": payload.get("recorded"),
                "prompt_tokens": payload.get("prompt_tokens"),
                "completion_tokens": payload.get("completion_tokens"),
            }
        )
        if action == "llm_call" and model:
            bucket = _model_bucket(model)
            entry = models.setdefault(
                bucket,
                {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0},
            )
            entry["calls"] += 1
            entry["prompt_tokens"] += int(payload.get("prompt_tokens") or 0)
            entry["completion_tokens"] += int(payload.get("completion_tokens") or 0)

    return {
        "events": events,
        "models": [
            {
                "role": name,
                "calls": stats["calls"],
                "prompt_tokens": stats["prompt_tokens"],
                "completion_tokens": stats["completion_tokens"],
            }
            for name, stats in sorted(models.items())
        ],
    }


def _payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _is_highlighted(action: str, payload: dict[str, Any]) -> bool:
    markers = (
        "approval",
        "awaiting",
        "blocked",
        "cancel_pending",
        "prepare_claim_failed",
        "prepare_claim_rejected",
    )
    blob = f"{action} {json.dumps(payload, ensure_ascii=False)}".lower()
    return any(m in blob for m in markers)


def _status(action: str, payload: dict[str, Any]) -> str:
    if _is_highlighted(action, payload):
        if "pending" in action or "awaiting" in str(payload).lower():
            return "awaiting-approval"
        if "fail" in action or "reject" in action:
            return "blocked"
        return "awaiting-approval"
    if payload.get("recorded") is True:
        return "recorded"
    if action.endswith("_failed") or action.endswith("_rejected"):
        return "blocked"
    return "ok"


def _model_bucket(model: str) -> str:
    lower = model.lower()
    if "ultra" in lower:
        return "Ultra"
    if "super" in lower:
        return "Super"
    if "nano" in lower:
        return "Nano"
    return model
