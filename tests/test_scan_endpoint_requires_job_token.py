"""T25 — Scan endpoint requires X-Job-Token when JOB_TOKEN is set."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "t25.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("RECORDED_MODE", "true")
    monkeypatch.setenv("JOB_TOKEN", "secret-job-token")
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_scan_endpoint_requires_job_token(client: TestClient) -> None:
    missing = client.post("/api/jobs/scan")
    assert missing.status_code == 401
    err = missing.json()["detail"]["error"]
    assert err["code"] == "job_token_required"

    wrong = client.post("/api/jobs/scan", headers={"X-Job-Token": "nope"})
    assert wrong.status_code == 401

    ok = client.post("/api/jobs/scan", headers={"X-Job-Token": "secret-job-token"})
    assert ok.status_code == 200
    assert "created" in ok.json()
