"""Simple in-process rate limiter (one uvicorn worker)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Sliding-window limiter keyed by an opaque string (usually client IP)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_s: float) -> bool:
        if limit <= 0:
            return False
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - window_s
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True
