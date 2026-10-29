"""Load demo/ into SQLite (idempotent)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

from app.clock import Clock, clock_from_settings
from app.config import Settings, get_settings
from app.db import connect, init_db
from app.ingest.subscriptions import apply_unused_flag
from app.money import dollars_to_cents

# Simple merchant labels for the demo statement (full Nano normalization is M1).
_MERCHANT_ALIASES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"DAILYNEWS", re.I), "DailyNews", "subscription"),
    (re.compile(r"STREAMFLIX", re.I), "StreamFlix", "subscription"),
    (re.compile(r"CLOUDNEST", re.I), "CloudNest", "subscription"),
    (re.compile(r"FITPULSE", re.I), "FitPulse", "subscription"),
    (re.compile(r"TUNEBOX", re.I), "TuneBox", "subscription"),
    (re.compile(r"REPLIT", re.I), "Replit", "purchase"),
    (re.compile(r"GREENMART", re.I), "GreenMart", "other"),
    (re.compile(r"CITY TRANSIT", re.I), "City Transit", "other"),
]


def _classify(merchant_raw: str) -> tuple[str, str]:
    for pattern, norm, category in _MERCHANT_ALIASES:
        if pattern.search(merchant_raw):
            return norm, category
    cleaned = re.sub(r"\s+", " ", merchant_raw).strip()
    return cleaned.title(), "other"


def _demo_path(demo_dir: Path, *parts: str) -> Path:
    path = demo_dir.joinpath(*parts)
    if path.exists():
        return path
    # Fallback if files still sit under receipts/ (older layout).
    alt = demo_dir / "receipts" / parts[-1]
    if alt.exists():
        return alt
    return path


def seed_statement(conn: sqlite3.Connection, demo_dir: Path) -> int:
    path = _demo_path(demo_dir, "statement.csv")
    if not path.exists():
        raise FileNotFoundError(f"missing statement: {path}")

    existing = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
    if existing:
        return 0

    inserted = 0
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            merchant_raw = row["description"].strip()
            merchant_norm, category = _classify(merchant_raw)
            amount_cents = dollars_to_cents(row["amount"])
            conn.execute(
                """
                INSERT INTO transactions
                    (date, merchant_raw, merchant_norm, amount_cents, currency, category)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["date"].strip(),
                    merchant_raw,
                    merchant_norm,
                    amount_cents,
                    row["currency"].strip(),
                    category,
                ),
            )
            inserted += 1
    return inserted


def seed_subscriptions(conn: sqlite3.Connection, demo_dir: Path) -> int:
    path = _demo_path(demo_dir, "subscription_usage.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    usage = data["usage"]

    existing = conn.execute("SELECT COUNT(*) AS n FROM subscriptions").fetchone()["n"]
    if existing:
        return 0

    # Monthly amounts from the statement (absolute value of subscription charges).
    monthly: dict[str, tuple[int, str, str]] = {}
    rows = conn.execute(
        """
        SELECT merchant_norm, ABS(amount_cents) AS amt, currency, MIN(date) AS started
        FROM transactions
        WHERE category = 'subscription'
        GROUP BY merchant_norm
        """
    ).fetchall()
    for row in rows:
        monthly[row["merchant_norm"]] = (row["amt"], row["currency"], row["started"])

    inserted = 0
    for entry in usage:
        merchant = entry["merchant"]
        amount_cents, currency, started = monthly.get(
            merchant, (0, "USD", entry.get("last_used_at") or "2026-01-01")
        )
        status = entry.get("status", "active")
        if status not in ("active", "flagged", "cancelled"):
            status = "active"
        conn.execute(
            """
            INSERT INTO subscriptions
                (merchant, merchant_norm, amount_monthly_cents, currency,
                 started_at, last_used_at, portal_template, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merchant,
                merchant,
                amount_cents,
                currency,
                started,
                entry.get("last_used_at"),
                entry.get("portal_template"),
                status,
            ),
        )
        portal_status = "cancelled" if status == "cancelled" else "active"
        conn.execute(
            """
            INSERT OR IGNORE INTO portal_accounts
                (merchant, portal_template, status, confirmation_no)
            VALUES (?, ?, ?, ?)
            """,
            (
                merchant,
                entry.get("portal_template") or "settings-menu",
                portal_status,
                "SEED-DN-001" if status == "cancelled" else None,
            ),
        )
        inserted += 1
    return inserted


def seed_skills(conn: sqlite3.Connection, demo_dir: Path) -> int:
    path = _demo_path(demo_dir, "seed_skills.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    inserted = 0
    for skill in data["skills"]:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO skills
                (name, merchant, portal_template, trigger, steps_json, sources_json,
                 success_count, learned_at, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                skill["name"],
                skill["merchant"],
                skill["portal_template"],
                skill["trigger"],
                json.dumps(skill["steps"], ensure_ascii=False),
                json.dumps(skill.get("sources", []), ensure_ascii=False),
                int(skill.get("success_count", 1)),
                skill["learned_at"],
                skill.get("last_used_at"),
            ),
        )
        inserted += cur.rowcount
    return inserted


def seed_savings(conn: sqlite3.Connection, demo_dir: Path, clock: Clock) -> int:
    path = _demo_path(demo_dir, "savings_plan.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    seeded_ids = set(data.get("seeded_before_demo", []))
    inserted = 0
    created_at = clock.now().isoformat()
    for event in data["events"]:
        if event["id"] not in seeded_ids:
            continue
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO savings_events
                (kind, merchant, amount_cents, time_saved_min, source_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event["kind"],
                event["merchant"],
                int(event["amount_cents"]),
                int(event["time_saved_min"]),
                event["id"],
                created_at,
            ),
        )
        inserted += cur.rowcount
    return inserted


def seed_all(
    conn: sqlite3.Connection,
    demo_dir: Path | str,
    clock: Clock | None = None,
) -> dict[str, int]:
    demo = Path(demo_dir)
    clock = clock or Clock(today="2026-10-27")
    init_db(conn)
    counts = {
        "transactions": seed_statement(conn, demo),
        "subscriptions": seed_subscriptions(conn, demo),
        "skills": seed_skills(conn, demo),
        "savings_events": seed_savings(conn, demo, clock),
    }
    apply_unused_flag(conn, clock)
    conn.commit()
    return counts


def run_seed(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    clock = clock_from_settings(settings.demo_today)
    conn = connect(settings.database_file())
    try:
        return seed_all(conn, Path(settings.demo_dir), clock)
    finally:
        conn.close()


def main() -> None:
    counts = run_seed()
    print("seed complete:", counts)


if __name__ == "__main__":
    main()
