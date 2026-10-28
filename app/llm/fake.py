"""FakeLLM: recorded responses and per-model call counters for tests."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class FakeLLM:
    """Lookup recorded responses by request hash; count calls per model."""

    def __init__(
        self,
        recordings: dict[str, Any] | Path | None = None,
        *,
        default_response: str | dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.call_counts: Counter[str] = Counter()
        self._recordings: dict[str, Any] = {}
        self._default = default_response
        if recordings is None:
            return
        if isinstance(recordings, Path):
            if recordings.is_file():
                data = json.loads(recordings.read_text(encoding="utf-8"))
                self._recordings = dict(data)
            elif recordings.is_dir():
                for path in recordings.glob("*.json"):
                    self._recordings[path.stem] = json.loads(
                        path.read_text(encoding="utf-8")
                    )
        else:
            self._recordings = dict(recordings)

    @property
    def ultra_calls(self) -> int:
        return sum(
            count
            for model, count in self.call_counts.items()
            if "ultra" in model.lower()
        )

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any:
        payload = {
            "model": model,
            "messages": messages,
            "prompt": prompt,
            **kwargs,
        }
        key = request_hash(
            {"model": model, "messages": messages, "prompt": prompt}
        )
        self.calls.append({"key": key, **payload})
        self.call_counts[model] += 1

        if key in self._recordings:
            return self._recordings[key]
        # Allow lookup by model name or free-form aliases in fixtures.
        for alias in (model, kwargs.get("recording_key"), prompt):
            if isinstance(alias, str) and alias in self._recordings:
                return self._recordings[alias]
        if self._default is not None:
            return self._default
        raise KeyError(f"no recorded LLM response for hash {key[:12]}…")
