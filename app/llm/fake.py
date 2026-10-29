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
        self.last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        self._recordings: dict[str, Any] = {}
        self._default = default_response
        if recordings is None:
            return
        if isinstance(recordings, Path):
            if recordings.is_file():
                data = json.loads(recordings.read_text(encoding="utf-8"))
                self._recordings = {
                    k: v for k, v in dict(data).items() if not str(k).startswith("_")
                }
            elif recordings.is_dir():
                index = recordings / "llm.json"
                if index.is_file():
                    data = json.loads(index.read_text(encoding="utf-8"))
                    self._recordings = {
                        k: v
                        for k, v in dict(data).items()
                        if not str(k).startswith("_")
                    }
                else:
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
            result = self._recordings[key]
        else:
            result = None
            # Allow lookup by model name or free-form aliases in fixtures.
            for alias in (model, kwargs.get("recording_key"), prompt):
                if isinstance(alias, str) and alias in self._recordings:
                    result = self._recordings[alias]
                    break
            if result is None and self._default is not None:
                result = self._default
            if result is None:
                raise KeyError(f"no recorded LLM response for hash {key[:12]}…")

        prompt_blob = prompt or json.dumps(messages or [], ensure_ascii=False)
        if isinstance(result, str):
            completion_blob = result
        else:
            completion_blob = json.dumps(result, ensure_ascii=False)
        self.last_usage = {
            "prompt_tokens": max(1, len(prompt_blob) // 4) if prompt_blob else 0,
            "completion_tokens": max(1, len(completion_blob) // 4)
            if completion_blob
            else 0,
        }
        return result
