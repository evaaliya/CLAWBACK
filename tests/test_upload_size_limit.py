"""T26 — Ingest rejects uploads over 1 MB or disallowed types."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "t26.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("RECORDED_MODE", "true")
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "1024")
    get_settings.cache_clear()
    with TestClient(app) as c:
        # Bind the low limit onto the live settings object (lifespan already ran).
        c.app.state.settings.upload_max_bytes = 1024
        yield c
    get_settings.cache_clear()


def test_upload_size_limit(client: TestClient) -> None:
    too_big = b"x" * 2048
    res = client.post(
        "/api/ingest/statement",
        files={"file": ("statement.csv", too_big, "text/csv")},
    )
    assert res.status_code == 400
    err = res.json()["detail"]["error"]
    assert err["code"] == "upload_too_large"

    bad_type = client.post(
        "/api/ingest/receipts",
        files={"files": ("malware.exe", b"MZ", "application/octet-stream")},
    )
    assert bad_type.status_code == 400
    err2 = bad_type.json()["detail"]["error"]
    assert err2["code"] == "upload_type_not_allowed"
