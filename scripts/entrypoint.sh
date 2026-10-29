#!/bin/sh
# Container entrypoint: ensure DB dir exists, seed on empty disk, serve with one worker.
set -eu

DB_PATH="${DATABASE_PATH:-/data/clawback.db}"
DB_DIR=$(dirname "$DB_PATH")
mkdir -p "$DB_DIR" "${CACHE_DIR:-/data/cache}"

# Nebius endpoint disk is ephemeral — seed whenever the DB file is missing or empty.
NEED_SEED=1
if [ -f "$DB_PATH" ]; then
  ROW_COUNT=$(python - <<PY
import sqlite3, os
path = os.environ.get("DATABASE_PATH", "/data/clawback.db")
try:
    conn = sqlite3.connect(path)
    n = conn.execute(
        "SELECT (SELECT COUNT(*) FROM sqlite_master WHERE type='table')"
    ).fetchone()[0]
    if n == 0:
        print(0)
    else:
        # Any demo table with rows counts as seeded.
        total = 0
        for t in ("transactions", "subscriptions", "savings_events"):
            try:
                total += conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                pass
        print(total)
    conn.close()
except Exception:
    print(0)
PY
)
  if [ "$ROW_COUNT" != "0" ]; then
    NEED_SEED=0
  fi
fi

if [ "$NEED_SEED" = "1" ]; then
  echo "entrypoint: seeding demo database at $DB_PATH"
  python -m app.seed
fi

# --workers 1 is mandatory: SSE broker and SQLite are in-process. No --reload.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
