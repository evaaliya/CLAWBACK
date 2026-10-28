"""T3 — Receipt becomes the SoundHub purchase; bad JSON → needs_review."""

from __future__ import annotations

import json
from pathlib import Path

from app.clock import Clock
from app.ingest.receipts import parse_and_store_receipt
from app.llm.fake import FakeLLM


SOUNDHUB_PARSED = {
    "merchant": "SoundHub",
    "item": "Wireless over-ear headphones SH-700",
    "date": "2026-09-30",
    "amount_cents": 23500,
    "currency": "USD",
    "return_deadline": "2026-10-30",
    "warranty_until": None,
    "confidence": 0.95,
}


def test_receipt_parse_fixture(conn, demo_dir: Path, clock: Clock) -> None:
    receipt_path = demo_dir / "receipts" / "soundhub-order-48213.txt"
    text = receipt_path.read_text(encoding="utf-8")
    llm = FakeLLM(
        recordings={
            "receipt:soundhub-order-48213.txt": json.dumps(SOUNDHUB_PARSED),
        }
    )

    purchase = parse_and_store_receipt(
        conn,
        text=text,
        llm=llm,
        clock=clock,
        receipt_path=str(receipt_path),
        recording_key="receipt:soundhub-order-48213.txt",
    )
    conn.commit()

    assert purchase["amount_cents"] == 23500
    assert purchase["return_deadline"] == "2026-10-30"
    assert purchase["merchant"] == "SoundHub"
    assert purchase["needs_review"] is False

    row = conn.execute(
        """
        SELECT merchant, item, amount_cents, currency, return_deadline,
               warranty_until, status, needs_review
        FROM purchases WHERE id = ?
        """,
        (purchase["id"],),
    ).fetchone()
    assert row is not None
    assert row["amount_cents"] == 23500
    assert row["return_deadline"] == "2026-10-30"
    assert row["needs_review"] == 0

    doc = conn.execute(
        "SELECT text FROM documents WHERE ref_type = 'purchase' AND ref_id = ?",
        (purchase["id"],),
    ).fetchone()
    assert doc is not None
    assert "SOUNDHUB" in doc["text"]
    assert "48213" in doc["text"]


def test_receipt_bad_json_needs_review(conn, clock: Clock) -> None:
    """Invalid JSON is retried once; second failure → needs_review."""
    calls: list[str] = []

    class FlakyLLM(FakeLLM):
        def complete(self, *, model, messages=None, prompt=None, **kwargs):
            calls.append(model)
            # Always return invalid JSON so validation fails twice.
            self.calls.append({"model": model})
            self.call_counts[model] += 1
            return "{not valid json"

    llm = FlakyLLM()
    purchase = parse_and_store_receipt(
        conn,
        text="SOME STORE\nTotal: $10.00\n",
        llm=llm,
        clock=clock,
        receipt_path="bad-receipt.txt",
        recording_key="receipt:bad",
    )
    conn.commit()

    assert len(calls) == 2  # initial + one retry
    assert purchase["needs_review"] is True
    row = conn.execute(
        "SELECT needs_review, amount_cents, merchant FROM purchases WHERE id = ?",
        (purchase["id"],),
    ).fetchone()
    assert row["needs_review"] == 1
