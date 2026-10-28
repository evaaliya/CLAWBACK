"""Parse statement CSV or JSON into row dicts."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.money import dollars_to_cents


def parse_statement(content: str | bytes, *, filename: str | None = None) -> list[dict[str, Any]]:
    """Return rows with date, merchant_raw, amount_cents, currency."""
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    text = text.strip()
    name = (filename or "").lower()

    if name.endswith(".json") or text.startswith("{") or text.startswith("["):
        return _from_json(text)
    return _from_csv(text)


def _from_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for row in reader:
        # Accept either "description" (demo) or "merchant" column names.
        merchant_raw = (row.get("description") or row.get("merchant") or "").strip()
        if not merchant_raw:
            continue
        rows.append(
            {
                "date": row["date"].strip(),
                "merchant_raw": merchant_raw,
                "amount_cents": dollars_to_cents(row["amount"]),
                "currency": row.get("currency", "USD").strip() or "USD",
            }
        )
    return rows


def _from_json(text: str) -> list[dict[str, Any]]:
    data = json.loads(text)
    items = data["transactions"] if isinstance(data, dict) and "transactions" in data else data
    rows: list[dict[str, Any]] = []
    for item in items:
        merchant_raw = (item.get("description") or item.get("merchant") or "").strip()
        amount = item.get("amount_cents", item.get("amount"))
        if "amount_cents" in item:
            amount_cents = int(item["amount_cents"])
        else:
            amount_cents = dollars_to_cents(amount)
        rows.append(
            {
                "date": str(item["date"]).strip(),
                "merchant_raw": merchant_raw,
                "amount_cents": amount_cents,
                "currency": str(item.get("currency", "USD")).strip() or "USD",
            }
        )
    return rows
