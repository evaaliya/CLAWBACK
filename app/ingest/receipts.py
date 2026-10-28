"""Receipt parsing with strict JSON schema, one retry, then needs_review."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError, field_validator

from app.agent_log import log_action
from app.clock import Clock


class ReceiptFields(BaseModel):
    merchant: str
    item: str
    date: str
    amount_cents: int
    currency: str = "USD"
    return_deadline: str | None = None
    warranty_until: str | None = None
    confidence: float = 0.0

    @field_validator("amount_cents")
    @classmethod
    def amount_must_be_int(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("amount_cents must be int")
        return value


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


def parse_and_store_receipt(
    conn: sqlite3.Connection,
    *,
    text: str,
    llm: LLMClient,
    clock: Clock,
    receipt_path: str | None = None,
    recording_key: str | None = None,
    model: str = "nano",
) -> dict[str, Any]:
    """Parse receipt text via Nano; retry once on invalid JSON; else needs_review."""
    key = recording_key or f"receipt:{receipt_path or 'upload'}"
    prompt = _receipt_prompt(text)
    parsed: ReceiptFields | None = None
    needs_review = False
    last_error: str | None = None

    for attempt in range(2):
        try:
            raw = llm.complete(
                model=model,
                prompt=prompt if attempt == 0 else _retry_prompt(prompt, last_error),
                recording_key=key,
            )
            parsed = ReceiptFields.model_validate(_as_dict(raw))
            needs_review = False
            break
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            last_error = str(exc)
            parsed = None
            needs_review = True

    if parsed is None:
        purchase_id = _insert_purchase(
            conn,
            merchant="unknown",
            item="needs_review",
            date=clock.today().isoformat(),
            amount_cents=0,
            currency="USD",
            return_deadline=None,
            warranty_until=None,
            receipt_path=receipt_path,
            needs_review=True,
        )
    else:
        purchase_id = _insert_purchase(
            conn,
            merchant=parsed.merchant,
            item=parsed.item,
            date=parsed.date,
            amount_cents=parsed.amount_cents,
            currency=parsed.currency,
            return_deadline=parsed.return_deadline,
            warranty_until=parsed.warranty_until,
            receipt_path=receipt_path,
            needs_review=needs_review or parsed.confidence < 0.5,
        )

    conn.execute(
        """
        INSERT INTO documents (ref_type, ref_id, text, embedding)
        VALUES ('purchase', ?, ?, NULL)
        """,
        (purchase_id, text),
    )
    log_action(
        conn,
        clock,
        actor="ingest",
        action="receipt_parse",
        payload={
            "purchase_id": purchase_id,
            "receipt_path": receipt_path,
            "needs_review": bool(
                needs_review if parsed is None else needs_review or parsed.confidence < 0.5
            ),
        },
    )

    row = conn.execute(
        "SELECT * FROM purchases WHERE id = ?", (purchase_id,)
    ).fetchone()
    assert row is not None
    return {
        "id": row["id"],
        "merchant": row["merchant"],
        "item": row["item"],
        "date": row["date"],
        "amount_cents": row["amount_cents"],
        "currency": row["currency"],
        "return_deadline": row["return_deadline"],
        "warranty_until": row["warranty_until"],
        "needs_review": bool(row["needs_review"]),
        "status": row["status"],
    }


def _insert_purchase(
    conn: sqlite3.Connection,
    *,
    merchant: str,
    item: str,
    date: str,
    amount_cents: int,
    currency: str,
    return_deadline: str | None,
    warranty_until: str | None,
    receipt_path: str | None,
    needs_review: bool,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline,
             warranty_until, receipt_path, status, needs_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """,
        (
            merchant,
            item,
            date,
            amount_cents,
            currency,
            return_deadline,
            warranty_until,
            receipt_path,
            1 if needs_review else 0,
        ),
    )
    return int(cur.lastrowid)


def _receipt_prompt(text: str) -> str:
    return (
        "Extract purchase fields from this receipt as JSON with keys: "
        "merchant, item, date (YYYY-MM-DD), amount_cents (int), currency, "
        "return_deadline, warranty_until, confidence. "
        "Never guess missing fields — use null. Amounts are integer cents.\n\n"
        f"{text}"
    )


def _retry_prompt(prompt: str, error: str | None) -> str:
    return (
        f"{prompt}\n\nPrevious output failed validation: {error}. "
        "Reply with valid JSON only."
    )


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise TypeError(f"unexpected LLM response type: {type(raw).__name__}")
