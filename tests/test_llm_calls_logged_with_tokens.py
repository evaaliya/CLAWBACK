"""T34 — Every LLM call is logged with token counts (no raw prompt)."""

from __future__ import annotations

import json

from app.clock import Clock
from app.ingest.receipts import parse_and_store_receipt
from app.llm.fake import FakeLLM


PARSED = {
    "merchant": "SoundHub",
    "item": "Headphones",
    "date": "2026-09-30",
    "amount_cents": 23500,
    "currency": "USD",
    "return_deadline": "2026-10-30",
    "warranty_until": None,
    "confidence": 0.9,
}


def test_llm_calls_logged_with_tokens(conn, clock: Clock) -> None:
    llm = FakeLLM(default_response=json.dumps(PARSED))
    parse_and_store_receipt(
        conn,
        text="SOUNDHUB\nPrice: $235.00 USD\nOrder date: 2026-09-30\n",
        llm=llm,
        clock=clock,
        receipt_path="log-receipt.txt",
        recording_key="receipt:log",
    )
    conn.commit()

    rows = conn.execute(
        """
        SELECT action, payload_json FROM agent_log
        WHERE action = 'llm_call'
        ORDER BY id
        """
    ).fetchall()
    assert rows, "expected llm_call rows in agent_log"
    for row in rows:
        payload = json.loads(row["payload_json"])
        assert "role" in payload
        assert "model" in payload
        assert isinstance(payload["prompt_tokens"], int)
        assert payload["prompt_tokens"] > 0
        assert isinstance(payload["completion_tokens"], int)
        assert payload["completion_tokens"] > 0
        assert isinstance(payload["latency_ms"], int)
        assert "recorded" in payload
        blob = json.dumps(payload)
        assert "SOUNDHUB" not in blob
        assert "prompt" not in payload
