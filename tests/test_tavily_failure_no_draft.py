"""T12 — Tavily or model failure → error card, no draft."""

from __future__ import annotations

from typing import Any

from app.claim_writer import prepare_claim
from app.clock import Clock
from app.llm.fake import FakeLLM
from app.search.fake import FakeSearch


def _insert_replit(conn) -> int:
    cur = conn.execute(
        """
        INSERT INTO purchases
            (merchant, item, date, amount_cents, currency, return_deadline, status)
        VALUES ('Replit', 'Core yearly subscription',
                '2026-09-30', 23500, 'USD', '2026-10-30', 'open')
        """
    )
    conn.commit()
    return int(cur.lastrowid)


class FailingSearch(FakeSearch):
    def search(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append({"query": query, **params})
        self.call_counts["search"] += 1
        raise RuntimeError("tavily unavailable")


class FailingLLM(FakeLLM):
    def complete(self, *, model, messages=None, prompt=None, **kwargs):
        self.calls.append({"model": model})
        self.call_counts[model] += 1
        raise RuntimeError("model unavailable")


def test_tavily_failure_no_draft(conn, clock: Clock) -> None:
    purchase_id = _insert_replit(conn)

    # Search failure: error card, no claim row, no fallback to model memory.
    search_fail = FailingSearch()
    llm_ok = FakeLLM(default_response='{"text":"from memory","citations":[]}')
    result_search = prepare_claim(
        conn,
        purchase_id=purchase_id,
        search=search_fail,
        llm=llm_ok,
        clock=clock,
        jurisdiction="US",
        model_ultra="ultra",
        model_super="super",
    )
    conn.commit()
    assert result_search["ok"] is False
    assert result_search["card"]["type"] == "error"
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM claims WHERE purchase_id = ?", (purchase_id,)
    ).fetchone()["n"] == 0

    # Model failure after successful search: same — no draft.
    search_ok = FakeSearch(
        default_results=[
            {
                "title": "Policy",
                "url": "https://replit.com/help/answers/refunds",
                "excerpt": "30-day return window for a full refund.",
            }
        ]
    )
    result_model = prepare_claim(
        conn,
        purchase_id=purchase_id,
        search=search_ok,
        llm=FailingLLM(),
        clock=clock,
        jurisdiction="US",
        model_ultra="ultra",
        model_super="super",
    )
    conn.commit()
    assert result_model["ok"] is False
    assert result_model["card"]["type"] == "error"
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM claims WHERE purchase_id = ?", (purchase_id,)
    ).fetchone()["n"] == 0
