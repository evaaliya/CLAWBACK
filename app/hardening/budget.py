"""Live LLM/search daily budget — falls back to recorded clients with a visible flag."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.clock import Clock


class LiveBudget:
    """Counts live model/search calls for the current demo day; persists beside the DB."""

    def __init__(
        self,
        *,
        limit: int,
        path: Path,
        clock: Clock,
    ) -> None:
        self.limit = max(0, int(limit))
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()
        self._day = clock.today().isoformat()
        self._count = 0
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if data.get("day") == self._day:
            self._count = int(data.get("count", 0))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"day": self._day, "count": self._count}),
            encoding="utf-8",
        )

    def _roll_day(self) -> None:
        today = self.clock.today().isoformat()
        if today != self._day:
            self._day = today
            self._count = 0

    @property
    def count(self) -> int:
        with self._lock:
            self._roll_day()
            return self._count

    @property
    def exhausted(self) -> bool:
        if self.limit <= 0:
            return True
        with self._lock:
            self._roll_day()
            return self._count >= self.limit

    def try_consume(self) -> bool:
        """Reserve one live call. Returns False when the budget is already exhausted."""
        if self.limit <= 0:
            return False
        with self._lock:
            self._roll_day()
            if self._count >= self.limit:
                return False
            self._count += 1
            self._save()
            return True

    def badge_flag(self) -> str | None:
        """UI badge text when forced into recorded responses by the budget."""
        if self.exhausted:
            return "recorded (live budget used)"
        return None


class BudgetAwareLLM:
    """Delegates to a live client until the daily budget is spent, then FakeLLM."""

    def __init__(
        self,
        *,
        live: Any,
        recorded: Any,
        budget: LiveBudget,
        force_recorded: bool = False,
    ) -> None:
        self._live = live
        self._recorded = recorded
        self._budget = budget
        self._force_recorded = force_recorded
        self._last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        self.calls: list[dict[str, Any]] = []
        self.call_counts = getattr(live, "call_counts", None) or getattr(
            recorded, "call_counts", None
        )

    @property
    def using_recorded(self) -> bool:
        return self._force_recorded or self._budget.exhausted

    @property
    def ultra_calls(self) -> int:
        for client in (self._live, self._recorded):
            if hasattr(client, "ultra_calls"):
                return int(client.ultra_calls)
        return 0

    def complete(self, **kwargs: Any) -> Any:
        if self._force_recorded or not self._budget.try_consume():
            result = self._recorded.complete(**kwargs)
            self.last_usage = dict(getattr(self._recorded, "last_usage", {}) or {})
            return result
        result = self._live.complete(**kwargs)
        self.last_usage = dict(getattr(self._live, "last_usage", {}) or {})
        return result

    @property
    def last_usage(self) -> dict[str, int]:
        return self._last_usage

    @last_usage.setter
    def last_usage(self, value: dict[str, int]) -> None:
        self._last_usage = dict(value or {})


class BudgetAwareSearch:
    """Same budget gate for Tavily / FakeSearch."""

    def __init__(
        self,
        *,
        live: Any,
        recorded: Any,
        budget: LiveBudget,
        force_recorded: bool = False,
    ) -> None:
        self._live = live
        self._recorded = recorded
        self._budget = budget
        self._force_recorded = force_recorded
        self.calls: list[dict[str, Any]] = getattr(live, "calls", [])

    @property
    def using_recorded(self) -> bool:
        return self._force_recorded or self._budget.exhausted

    def search(self, *args: Any, **kwargs: Any) -> Any:
        if self._force_recorded or not self._budget.try_consume():
            return self._recorded.search(*args, **kwargs)
        return self._live.search(*args, **kwargs)
