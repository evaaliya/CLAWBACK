"""Serverless Job entrypoint. Calls the same scan() as POST /jobs/scan."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clock import clock_from_settings
from app.config import get_settings
from app.db import connect, init_db
from app.deadline_watcher import scan


def main() -> None:
    settings = get_settings()
    clock = clock_from_settings(settings.demo_today)
    conn = connect(settings.database_file())
    try:
        init_db(conn)
        result = scan(
            conn,
            clock,
            hot_deadline_days=settings.hot_deadline_days,
        )
        conn.commit()
    finally:
        conn.close()
    print(
        "scan complete:",
        {
            "day": result["day"],
            "created": result["created"],
            "expired": len(result["expired"]),
            "notifications": len(result["notifications"]),
        },
    )


if __name__ == "__main__":
    main()
