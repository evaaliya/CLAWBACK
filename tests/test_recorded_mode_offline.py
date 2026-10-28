"""T20 — Golden Path runs in recorded mode with the network blocked."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.claim_writer import accept_refund, approve_claim, prepare_claim
from app.clock import Clock
from app.config import Settings
from app.deadline_watcher import scan
from app.ingest.service import ingest_receipts
from app.llm.factory import build_llm, recorded_llm_path
from app.llm.fake import FakeLLM
from app.savings.query import savings_summary
from app.search.factory import build_search, recorded_search_path
from app.search.fake import FakeSearch
from app.skill_forge.cancel import confirm_cancel, start_cancel


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any outbound HTTP so recorded clients cannot cheat."""

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("network blocked in recorded-mode test")

    monkeypatch.setattr(httpx.Client, "request", _blocked)
    monkeypatch.setattr(httpx.Client, "send", _blocked)
    monkeypatch.setattr(httpx, "request", _blocked)
    monkeypatch.setattr(httpx, "post", _blocked)
    monkeypatch.setattr(httpx, "get", _blocked)


def _sub_id(conn, merchant: str) -> int:
    row = conn.execute(
        "SELECT id FROM subscriptions WHERE merchant = ?",
        (merchant,),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def _cancel(conn, clock: Clock, llm: FakeLLM, merchant: str) -> None:
    sub_id = _sub_id(conn, merchant)
    start_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    confirm_cancel(
        conn,
        subscription_id=sub_id,
        llm=llm,
        clock=clock,
        model_ultra="ultra",
    )
    conn.commit()


def test_recorded_mode_offline(seeded_conn, clock: Clock, block_network, demo_dir: Path) -> None:
    settings = Settings(
        recorded_mode=True,
        demo_dir=str(demo_dir),
        nebius_api_key="should-not-be-used",
        tavily_api_key="should-not-be-used",
    )
    assert recorded_llm_path(settings).is_file()
    assert recorded_search_path(settings).is_file()

    llm = build_llm(settings)
    search = build_search(settings)
    assert isinstance(llm, FakeLLM)
    assert isinstance(search, FakeSearch)

    conn = seeded_conn
    opening = savings_summary(conn)
    assert opening["amount_cents"] == 9_600

    receipt = (demo_dir / "receipts" / "soundhub-order-48213.txt").read_text(
        encoding="utf-8"
    )
    ingest_receipts(
        conn,
        [
            {
                "text": receipt,
                "filename": "soundhub-order-48213.txt",
                "recording_key": "receipt:soundhub-order-48213.txt",
            }
        ],
        llm=llm,
        clock=clock,
        model="nano",
    )
    conn.commit()

    _cancel(conn, clock, llm, "StreamFlix")
    _cancel(conn, clock, llm, "CloudNest")

    scan(conn, clock)
    conn.commit()

    purchase = conn.execute(
        "SELECT id FROM purchases WHERE merchant = 'SoundHub' LIMIT 1"
    ).fetchone()
    assert purchase is not None
    prepared = prepare_claim(
        conn,
        purchase_id=int(purchase["id"]),
        search=search,
        llm=llm,
        clock=clock,
        jurisdiction="US",
        model_ultra="ultra",
        model_super="super",
    )
    conn.commit()
    approve_claim(conn, claim_id=prepared["claim_id"], clock=clock)
    conn.commit()
    accept_refund(conn, merchant="SoundHub", clock=clock)
    conn.commit()

    _cancel(conn, clock, llm, "FitPulse")

    counter = savings_summary(conn)
    assert counter["amount_cents"] == 84_700
    assert counter["time_saved_min"] == 360
    assert search.call_counts["search"] >= 1
    assert any(c.get("recording_key") == "claim:draft" for c in llm.calls)
    assert any(c.get("recording_key") == "cancel:plan:StreamFlix" for c in llm.calls)
