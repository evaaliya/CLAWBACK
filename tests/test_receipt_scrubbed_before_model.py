"""T33 — Receipt text is scrubbed before any model call; raw stays in documents."""

from __future__ import annotations

import json

from app.clock import Clock
from app.ingest.receipts import parse_and_store_receipt
from app.llm.fake import FakeLLM


RECEIPT = """\
ACME SOFTWARE
Order confirmation

Order number: 99
Order date: 2026-09-30
Payment: card ending 4417
Customer: Aliya Karimova <aliya.k@example.com>
Phone: +1-555-010-9988

Item: Pro yearly subscription
Quantity: 1
Price: $235.00 USD

Ship to: Aliya K., 12 Lenin Street, Bishkek
"""

PARSED = {
    "merchant": "Acme Software",
    "item": "Pro yearly subscription",
    "date": "2026-09-30",
    "amount_cents": 23500,
    "currency": "USD",
    "return_deadline": "2026-10-30",
    "warranty_until": None,
    "confidence": 0.95,
}


def test_receipt_scrubbed_before_model(conn, clock: Clock) -> None:
    llm = FakeLLM(default_response=json.dumps(PARSED))

    purchase = parse_and_store_receipt(
        conn,
        text=RECEIPT,
        llm=llm,
        clock=clock,
        receipt_path="pii-receipt.txt",
        recording_key="receipt:pii",
    )
    conn.commit()

    assert llm.calls, "expected at least one model call"
    prompt = llm.calls[0].get("prompt") or ""
    assert "4417" not in prompt
    assert "Aliya" not in prompt
    assert "aliya.k@example.com" not in prompt
    assert "Lenin" not in prompt
    assert "[LAST4]" in prompt or "[CARD]" in prompt
    assert "[REDACTED]" in prompt
    assert "[PHONE]" in prompt

    doc = conn.execute(
        "SELECT text FROM documents WHERE ref_type = 'purchase' AND ref_id = ?",
        (purchase["id"],),
    ).fetchone()
    assert doc is not None
    assert "4417" in doc["text"]
    assert "Aliya" in doc["text"]
