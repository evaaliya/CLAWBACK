"""Orchestrate statement and receipt ingest."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Protocol

from app.agent_log import log_action
from app.clock import Clock
from app.ingest.normalize import normalize_merchant
from app.ingest.receipts import parse_and_store_receipt
from app.ingest.statement import parse_statement
from app.ingest.subscriptions import (
    apply_unused_flag,
    apply_usage_signals,
    detect_subscriptions,
    list_subscriptions,
    upsert_subscriptions,
)


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


def ingest_statement(
    conn: sqlite3.Connection,
    content: str | bytes,
    *,
    llm: LLMClient,
    clock: Clock,
    filename: str | None = None,
    usage_path: Path | str | None = None,
    model: str = "nano",
) -> dict[str, Any]:
    rows = parse_statement(content, filename=filename)
    inserted = 0
    for row in rows:
        norm = normalize_merchant(llm, row["merchant_raw"], model=model)
        conn.execute(
            """
            INSERT INTO transactions
                (date, merchant_raw, merchant_norm, amount_cents, currency, category)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["date"],
                row["merchant_raw"],
                norm.merchant_norm,
                row["amount_cents"],
                row["currency"],
                norm.category,
            ),
        )
        inserted += 1

    detected = detect_subscriptions(conn)
    upsert_subscriptions(conn, detected)
    apply_usage_signals(conn, usage_path)
    apply_unused_flag(conn, clock)

    subs = list_subscriptions(conn)
    active_count = sum(1 for s in subs if s["status"] in ("active", "flagged"))
    cancelled_count = sum(1 for s in subs if s["status"] == "cancelled")
    flagged = [s for s in subs if s["status"] == "flagged"]

    log_action(
        conn,
        clock,
        actor="ingest",
        action="ingest_statement",
        payload={
            "transactions_inserted": inserted,
            "subscription_count": len(subs),
            "active_count": active_count,
            "cancelled_count": cancelled_count,
            "flagged_merchants": [s["merchant_norm"] for s in flagged],
        },
    )
    return {
        "transactions_inserted": inserted,
        "subscription_count": len(subs),
        "active_count": active_count,
        "cancelled_count": cancelled_count,
        "subscriptions": subs,
    }


def ingest_receipts(
    conn: sqlite3.Connection,
    items: list[dict[str, Any]],
    *,
    llm: LLMClient,
    clock: Clock,
    model: str = "nano",
) -> dict[str, Any]:
    """items: [{text, filename?, recording_key?}, ...]."""
    purchases: list[dict[str, Any]] = []
    for item in items:
        filename = item.get("filename") or item.get("receipt_path")
        key = item.get("recording_key")
        if key is None and filename:
            key = f"receipt:{Path(filename).name}"
        purchase = parse_and_store_receipt(
            conn,
            text=item["text"],
            llm=llm,
            clock=clock,
            receipt_path=filename,
            recording_key=key,
            model=model,
        )
        purchases.append(purchase)
    return {"purchases": purchases, "count": len(purchases)}
