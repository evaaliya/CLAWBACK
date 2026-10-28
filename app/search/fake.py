"""FakeSearch: recorded Tavily-style results and call counters."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def search_hash(query: str, **params: Any) -> str:
    raw = json.dumps({"query": query, **params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class FakeSearch:
    """Lookup recorded search results by request hash."""

    def __init__(
        self,
        recordings: dict[str, Any] | Path | None = None,
        *,
        default_results: list[dict[str, Any]] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.call_counts: Counter[str] = Counter()
        self._recordings: dict[str, Any] = {}
        self._default = default_results
        if recordings is None:
            return
        if isinstance(recordings, Path):
            if recordings.is_file():
                self._recordings = json.loads(recordings.read_text(encoding="utf-8"))
            elif recordings.is_dir():
                for path in recordings.glob("*.json"):
                    self._recordings[path.stem] = json.loads(
                        path.read_text(encoding="utf-8")
                    )
        else:
            self._recordings = dict(recordings)

    def search(self, query: str, **params: Any) -> list[dict[str, Any]]:
        key = search_hash(query, **params)
        self.calls.append({"key": key, "query": query, **params})
        self.call_counts["search"] += 1

        if key in self._recordings:
            return list(self._recordings[key])
        if query in self._recordings:
            return list(self._recordings[query])
        if self._default is not None:
            return list(self._default)
        raise KeyError(f"no recorded search response for hash {key[:12]}…")
