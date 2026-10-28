"""Recurring-charge detection and unused-subscription flagging."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from app.clock import Clock
from app.rules import UNUSED_DAYS

# Accept ~30-day cadence with a few days of slack; also ~annual.
_MONTHLY_MIN = 25
_MONTHLY_MAX = 35
_ANNUAL_MIN = 360
_ANNUAL_MAX = 370


def days_since_used(today: date, last_used: date) -> int:
    return (today - last_used).days


def detect_subscriptions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Find subscription groups: same merchant_norm + amount, ≥2 charges ~30d apart."""
    rows = conn.execute(
        """
        SELECT id, date, merchant_norm, amount_cents, currency, category
        FROM transactions
        ORDER BY merchant_norm, date
        """
    ).fetchall()

    groups: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        # Charges are negative on statements; compare absolute monthly amount.
        key = (row["merchant_norm"], abs(int(row["amount_cents"])))
        groups[key].append(row)

    found: list[dict[str, Any]] = []
    for (merchant_norm, amount_abs), items in groups.items():
        if len(items) < 2:
            continue
        if not _has_recurring_interval(items):
            continue
        currency = items[0]["currency"]
        started = min(date.fromisoformat(i["date"]) for i in items).isoformat()
        found.append(
            {
                "merchant": merchant_norm,
                "merchant_norm": merchant_norm,
                "amount_monthly_cents": amount_abs,
                "currency": currency,
                "started_at": started,
            }
        )
    return found


def _has_recurring_interval(items: list[sqlite3.Row]) -> bool:
    dates = sorted(date.fromisoformat(i["date"]) for i in items)
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i - 1]).days
        if _MONTHLY_MIN <= delta <= _MONTHLY_MAX:
            return True
        if _ANNUAL_MIN <= delta <= _ANNUAL_MAX:
            return True
    return False


def upsert_subscriptions(
    conn: sqlite3.Connection,
    detected: list[dict[str, Any]],
) -> None:
    for sub in detected:
        existing = conn.execute(
            "SELECT id FROM subscriptions WHERE merchant_norm = ?",
            (sub["merchant_norm"],),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE subscriptions
                SET amount_monthly_cents = ?, currency = ?, started_at = ?,
                    merchant = ?
                WHERE id = ?
                """,
                (
                    sub["amount_monthly_cents"],
                    sub["currency"],
                    sub["started_at"],
                    sub["merchant"],
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO subscriptions
                    (merchant, merchant_norm, amount_monthly_cents, currency,
                     started_at, last_used_at, portal_template, status)
                VALUES (?, ?, ?, ?, ?, NULL, NULL, 'active')
                """,
                (
                    sub["merchant"],
                    sub["merchant_norm"],
                    sub["amount_monthly_cents"],
                    sub["currency"],
                    sub["started_at"],
                ),
            )


def apply_usage_signals(
    conn: sqlite3.Connection,
    usage_path: Path | str | None,
) -> None:
    """Attach last_used_at / portal_template / cancelled from demo usage file."""
    if usage_path is None:
        return
    path = Path(usage_path)
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data.get("usage", []):
        merchant = entry["merchant"]
        status = entry.get("status", "active")
        if status not in ("active", "flagged", "cancelled"):
            status = "active"
        row = conn.execute(
            "SELECT id, status FROM subscriptions WHERE merchant_norm = ?",
            (merchant,),
        ).fetchone()
        if row is None:
            continue
        # Usage file is authoritative for cancelled; otherwise keep current
        # status so unused flagging can set flagged later.
        new_status = "cancelled" if status == "cancelled" else row["status"]
        if new_status not in ("active", "flagged", "cancelled"):
            new_status = "active"
        conn.execute(
            """
            UPDATE subscriptions
            SET last_used_at = ?, portal_template = ?, status = ?
            WHERE id = ?
            """,
            (
                entry.get("last_used_at"),
                entry.get("portal_template"),
                new_status,
                row["id"],
            ),
        )
        portal_status = "cancelled" if new_status == "cancelled" else "active"
        conn.execute(
            """
            INSERT INTO portal_accounts (merchant, portal_template, status, confirmation_no)
            VALUES (?, ?, ?, NULL)
            ON CONFLICT(merchant) DO UPDATE SET
                portal_template = excluded.portal_template,
                status = excluded.status
            """,
            (
                merchant,
                entry.get("portal_template") or "settings-menu",
                portal_status,
            ),
        )


def apply_unused_flag(conn: sqlite3.Connection, clock: Clock) -> None:
    """Flag subscriptions whose last_used_at is strictly older than UNUSED_DAYS.

    Missing last_used_at means usage is unknown — never treat as unused.
    Cancelled rows are left alone.
    """
    today = clock.today()
    rows = conn.execute(
        "SELECT id, last_used_at, status FROM subscriptions"
    ).fetchall()
    for row in rows:
        if row["status"] == "cancelled":
            continue
        last = row["last_used_at"]
        if not last:
            # Unknown usage → keep/ensure active (not flagged).
            if row["status"] == "flagged":
                conn.execute(
                    "UPDATE subscriptions SET status = 'active' WHERE id = ?",
                    (row["id"],),
                )
            continue
        last_date = date.fromisoformat(last)
        age = days_since_used(today, last_date)
        if age > UNUSED_DAYS:
            conn.execute(
                "UPDATE subscriptions SET status = 'flagged' WHERE id = ?",
                (row["id"],),
            )
        else:
            conn.execute(
                "UPDATE subscriptions SET status = 'active' WHERE id = ?",
                (row["id"],),
            )


def list_subscriptions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, merchant, merchant_norm, amount_monthly_cents, currency,
               started_at, last_used_at, portal_template, status
        FROM subscriptions
        ORDER BY merchant_norm
        """
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["unused"] = row["status"] == "flagged"
        out.append(item)
    return out
