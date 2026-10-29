"""T27 — Live LLM daily budget exhaustion falls back to recorded with a visible badge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.clock import Clock
from app.config import Settings, get_settings
from app.hardening.budget import BudgetAwareLLM, LiveBudget
from app.llm.fake import FakeLLM
from app.main import app


class CountingLiveLLM:
    """Stand-in for NebiusLLM that must not be called after the budget is spent."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.call_counts: dict[str, int] = {}

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        model = kwargs.get("model", "live")
        self.call_counts[model] = self.call_counts.get(model, 0) + 1
        return '{"ok": true}'


def test_live_budget_falls_back_visibly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, demo_dir: Path
) -> None:
    db = tmp_path / "t27.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("RECORDED_MODE", "false")
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("LIVE_LLM_DAILY_LIMIT", "2")
    get_settings.cache_clear()

    live = CountingLiveLLM()
    recorded = FakeLLM(
        {  # unused keys — FakeLLM falls through to default
        },
        default_response='{"from":"recorded"}',
    )
    clock = Clock(today="2026-10-27")
    budget = LiveBudget(limit=2, path=tmp_path / "budget.json", clock=clock)
    guarded = BudgetAwareLLM(live=live, recorded=recorded, budget=budget)

    # Two live calls consume the budget.
    assert guarded.complete(model="nano", prompt="a") == '{"ok": true}'
    assert guarded.complete(model="nano", prompt="b") == '{"ok": true}'
    assert len(live.calls) == 2
    assert budget.exhausted is True
    assert budget.badge_flag() == "recorded (live budget used)"

    # Further calls must not hit the live client.
    out = guarded.complete(model="nano", prompt="c")
    assert out == '{"from":"recorded"}'
    assert len(live.calls) == 2

    # Health exposes the badge flag for the UI.
    with TestClient(app) as client:
        client.app.state.budget = budget
        client.app.state.settings.recorded_mode = False
        client.app.state.llm = guarded
        health = client.get("/api/health").json()
        assert health["live_budget_exhausted"] is True
        assert health["badge"] == "recorded (live budget used)"
        assert health["recorded_mode"] is True

    get_settings.cache_clear()
