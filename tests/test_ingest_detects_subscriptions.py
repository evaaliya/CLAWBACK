"""T1 — Statement yields 4 active subscriptions and recognizes the cancelled one."""

from __future__ import annotations

from pathlib import Path

from app.clock import Clock
from app.ingest.service import ingest_statement
from app.llm.fake import FakeLLM


def test_ingest_detects_subscriptions(conn, demo_dir: Path, clock: Clock) -> None:
    # Recorded Nano normalizations keyed by merchant_raw (recording_key).
    llm = FakeLLM(recordings=_demo_normalize_recordings(demo_dir))


    result = ingest_statement(
        conn,
        (demo_dir / "statement.csv").read_text(encoding="utf-8"),
        llm=llm,
        clock=clock,
        usage_path=demo_dir / "subscription_usage.json",
    )
    conn.commit()

    subs = conn.execute(
        """
        SELECT merchant_norm, status, amount_monthly_cents
        FROM subscriptions
        ORDER BY merchant_norm
        """
    ).fetchall()
    by_name = {row["merchant_norm"]: row for row in subs}

    active_or_flagged = [
        s for s in subs if s["status"] in ("active", "flagged")
    ]
    assert len(active_or_flagged) == 4
    assert set(s["merchant_norm"] for s in active_or_flagged) == {
        "StreamFlix",
        "CloudNest",
        "FitPulse",
        "TuneBox",
    }

    assert "DailyNews" in by_name
    assert by_name["DailyNews"]["status"] == "cancelled"

    assert by_name["StreamFlix"]["amount_monthly_cents"] == 1500
    assert by_name["CloudNest"]["amount_monthly_cents"] == 1600
    assert by_name["FitPulse"]["amount_monthly_cents"] == 1200
    assert by_name["TuneBox"]["amount_monthly_cents"] == 1000
    assert by_name["DailyNews"]["amount_monthly_cents"] == 800

    assert result["subscription_count"] == 5
    assert result["active_count"] == 4


def _demo_normalize_recordings(demo_dir: Path) -> dict:
    """Map each statement description to a recorded Nano JSON response."""
    import csv

    alias = {
        "DAILYNEWS": ("DailyNews", "subscription"),
        "STREAMFLIX": ("StreamFlix", "subscription"),
        "CLOUDNEST": ("CloudNest", "subscription"),
        "FITPULSE": ("FitPulse", "subscription"),
        "TUNEBOX": ("TuneBox", "subscription"),
        "SOUNDHUB": ("SoundHub", "purchase"),
        "GREENMART": ("GreenMart", "other"),
        "CITY TRANSIT": ("City Transit", "other"),
    }
    out: dict = {}
    with (demo_dir / "statement.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw = row["description"].strip()
            for key, (norm, cat) in alias.items():
                if key in raw.upper():
                    out[f"normalize:{raw}"] = {
                        "merchant_norm": norm,
                        "category": cat,
                    }
                    break
    return out
