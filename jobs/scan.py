"""Serverless Job entrypoint.

If SCAN_TARGET_URL is set, POST that deployment's /api/jobs/scan (shared DB on
the endpoint). Otherwise run scan() against the local SQLite file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clock import clock_from_settings
from app.config import get_settings
from app.db import connect, init_db
from app.deadline_watcher import scan


def _remote_scan(target_url: str, job_token: str) -> dict:
    base = target_url.rstrip("/")
    url = f"{base}/api/jobs/scan"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if job_token:
        headers["X-Job-Token"] = job_token
    req = Request(url, data=b"{}", headers=headers, method="POST")
    with urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def main() -> None:
    settings = get_settings()
    target = (settings.scan_target_url or "").strip()
    if target:
        try:
            result = _remote_scan(target, settings.job_token or "")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"remote scan failed: HTTP {exc.code} {detail}", file=sys.stderr)
            sys.exit(1)
        except (URLError, json.JSONDecodeError, TimeoutError) as exc:
            print(f"remote scan failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, ensure_ascii=False))
        return

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
