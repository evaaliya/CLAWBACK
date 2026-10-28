"""Shared pytest fixtures. Database is real SQLite; never mocked."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clock import Clock
from app.db import connect, init_db
from app.seed import seed_all


@pytest.fixture
def demo_dir() -> Path:
    return ROOT / "demo"


@pytest.fixture
def clock() -> Clock:
    return Clock(today="2026-10-27")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path):
    connection = connect(db_path)
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def seeded_conn(conn, demo_dir: Path, clock: Clock):
    seed_all(conn, demo_dir, clock)
    return conn
