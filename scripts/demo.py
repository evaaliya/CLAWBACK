"""Reset the database to the seeded demo state (`make demo`)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clock import clock_from_settings
from app.config import get_settings
from app.db import connect, init_db
from app.demo_reset import wipe_and_seed


def main() -> None:
    settings = get_settings()
    db_path = settings.database_file()
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            side.unlink()
    conn = connect(db_path)
    try:
        init_db(conn)
        clock = clock_from_settings(settings.demo_today)
        counts = wipe_and_seed(conn, Path(settings.demo_dir), clock)
    finally:
        conn.close()
    print("demo reset:", counts)


if __name__ == "__main__":
    main()
