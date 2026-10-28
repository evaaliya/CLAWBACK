"""T10 — Nothing is sent without approval."""

from __future__ import annotations

import json
import pytest

from app.claim_writer import ApprovalRequired, prepare_claim, send_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.search.fake import FakeSearch


SOUNDHUB_SOURCES = [
    {
        "title": "SoundHub Returns and Refunds (fixture)",
        "url": "https://example.com/soundhub/returns",
        "excerpt": (
            "Unused or lightly used items can be returned within 30 days "
            "of purchase for a full refund to the original payment method. "
            "Contact support with your order number."
        ),
    }
]


def _insert_soundhub(conn) -> int:
    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('SoundHub', 'Wireless over-ear headphones SH-700',
                '2026-09-30', 23500, 'USD', '2026-10-30', 'open')
        """
    )
    conn.commit()
    return int(cur.lastrowid)


def _good_draft() -> dict:
    return {
        "text": (
            "Please refund my Wireless over-ear headphones SH-700 purchased on "
            "2026-09-30 for 23500 cents (USD). Your policy allows unused items "
            "to be returned within 30 days for a full refund."
        ),
        "citations": [
            {
                "title": "SoundHub Returns and Refunds (fixture)",
                "url": "https://example.com/soundhub/returns",
                "excerpt": (
                    "Unused or lightly used items can be returned within 30 days "
                    "of purchase for a full refund to the original payment method."
                ),
            }
        ],
    }


def test_send_requires_approval(conn, clock: Clock) -> None:
    purchase_id = _insert_soundhub(conn)
    search = FakeSearch(
        recordings={"SoundHub return refund policy US": SOUNDHUB_SOURCES}
    )
    llm = FakeLLM(
        recordings={
            "claim:draft": json.dumps(_good_draft()),
            "claim:validate": json.dumps({"ok": True, "reasons": []}),
        }
    )
    result = prepare_claim(
        conn,
        purchase_id=purchase_id,
        search=search,
        llm=llm,
        clock=clock,
        jurisdiction="US",
        model_ultra="ultra",
        model_super="super",
    )
    conn.commit()
    assert result["ok"] is True
    claim_id = result["claim_id"]

    with pytest.raises(ApprovalRequired):
        send_claim(conn, claim_id=claim_id, clock=clock)

    outbox = conn.execute("SELECT COUNT(*) AS n FROM outbox").fetchone()
    assert outbox["n"] == 0
    status = conn.execute(
        "SELECT status FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()["status"]
    assert status == "draft"
