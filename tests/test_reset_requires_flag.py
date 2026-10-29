"""T24 — Demo reset requires DEMO_RESET=enabled."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "t24.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("RECORDED_MODE", "true")
    monkeypatch.setenv("DEMO_RESET", "")
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_reset_requires_flag(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    res = client.post("/api/demo/reset")
    assert res.status_code == 403
    body = res.json()
    err = body.get("detail", {}).get("error") or body.get("error")
    assert err["code"] == "demo_reset_disabled"

    monkeypatch.setenv("DEMO_RESET", "enabled")
    get_settings.cache_clear()
    # Settings are bound at lifespan; flip on the live app state for this process.
    client.app.state.settings.demo_reset = "enabled"
    res_ok = client.post("/api/demo/reset")
    assert res_ok.status_code == 200
    assert res_ok.json().get("ok") is True
