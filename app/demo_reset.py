"""Reset SQLite to the seeded demo state (used by make demo and /api/demo/reset)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.clock import Clock
from app.db import init_db
from app.seed import seed_all

# Order matters for FK-free SQLite: children first.
_TABLES = (
    "agent_log",
    "notifications",
    "outbox",
    "claims",
    "savings_events",
    "skills",
    "documents",
    "purchases",
    "subscriptions",
    "transactions",
    "portal_accounts",
)


def wipe_and_seed(
    conn: sqlite3.Connection,
    demo_dir: Path | str,
    clock: Clock,
) -> dict[str, int]:
    """Clear all app tables and re-run seed_all (keeps the same DB file)."""
    init_db(conn)
    for table in _TABLES:
        conn.execute(f"DELETE FROM {table}")
    counts = seed_all(conn, demo_dir, clock)
    conn.commit()
    return counts
