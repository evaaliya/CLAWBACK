"""SQLite connection and schema (SPEC section 3). WAL mode on."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY,
    merchant TEXT NOT NULL,
    merchant_norm TEXT NOT NULL,
    amount_monthly_cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    started_at DATE NOT NULL,
    last_used_at DATE,
    portal_template TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'flagged', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL,
    merchant_raw TEXT NOT NULL,
    merchant_norm TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('subscription', 'purchase', 'other'))
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY,
    merchant TEXT NOT NULL,
    item TEXT NOT NULL,
    date DATE NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    return_deadline DATE,
    warranty_until DATE,
    receipt_path TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'claimed', 'expired', 'done')),
    needs_review INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    ref_type TEXT NOT NULL,
    ref_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY,
    purchase_id INTEGER NOT NULL,
    draft_text TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'sent', 'refund_accepted', 'rejected')),
    approved_at TEXT,
    amount_recovered_cents INTEGER
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    claim_id INTEGER NOT NULL UNIQUE,
    to_address TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'delivered', 'refund_accepted')),
    queued_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    merchant TEXT NOT NULL,
    portal_template TEXT NOT NULL,
    trigger TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 1,
    learned_at DATE NOT NULL,
    last_used_at DATE
);

CREATE TABLE IF NOT EXISTS portal_accounts (
    merchant TEXT PRIMARY KEY,
    portal_template TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'cancelled')),
    confirmation_no TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    purchase_id INTEGER,
    day DATE NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    seen_at TEXT,
    UNIQUE (kind, purchase_id, day)
);

CREATE TABLE IF NOT EXISTS savings_events (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('cancel', 'refund')),
    merchant TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    time_saved_min INTEGER NOT NULL,
    source_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""

# Money columns that must be INTEGER (T4).
MONEY_COLUMNS: dict[str, set[str]] = {
    "subscriptions": {"amount_monthly_cents"},
    "transactions": {"amount_cents"},
    "purchases": {"amount_cents"},
    "claims": {"amount_recovered_cents"},
    "savings_events": {"amount_cents"},
}


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def money_column_types(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """Return declared affinity for each money column (for T4)."""
    result: dict[str, dict[str, str]] = {}
    for table, columns in MONEY_COLUMNS.items():
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        result[table] = {}
        for row in rows:
            name = row["name"]
            if name in columns:
                result[table][name] = row["type"].upper()
    return result


def check_db(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
