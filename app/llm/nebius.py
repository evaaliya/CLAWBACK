"""Nebius Token Factory client (OpenAI-compatible).

Docs: https://docs.tokenfactory.nebius.com/quickstart
Cookbook: https://github.com/nebius/token-factory-cookbook
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from openai import OpenAI

# Verified against Token Factory quickstart + model catalog (2026-10-28).
DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
DEFAULT_MODEL_NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
DEFAULT_MODEL_SUPER = "nvidia/nemotron-3-super-120b-a12b"
DEFAULT_MODEL_ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"


class NebiusLLM:
    """Thin OpenAI-compatible wrapper with the same surface as FakeLLM.complete."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("NEBIUS_API_KEY is required for NebiusLLM")
        self.calls: list[dict[str, Any]] = []
        self.call_counts: Counter[str] = Counter()
        self.last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or DEFAULT_BASE_URL,
            timeout=timeout,
        )

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
    ) -> str:
        chat_messages = list(messages) if messages else []
        if prompt is not None and not chat_messages:
            chat_messages = [{"role": "user", "content": prompt}]
        if not chat_messages:
            raise ValueError("complete() needs messages or prompt")

        # recording_key is only for FakeLLM / cache; strip before the HTTP call.
        kwargs.pop("recording_key", None)

        # Nemotron "thinking" can fill the budget and leave content=null.
        # For structured ingest JSON we want the final answer only.
        enable_thinking = bool(kwargs.pop("enable_thinking", False))
        if "max_tokens" not in kwargs:
            kwargs["max_tokens"] = 1024
        extra_body = dict(kwargs.pop("extra_body", None) or {})
        tmpl = dict(extra_body.get("chat_template_kwargs") or {})
        tmpl.setdefault("enable_thinking", enable_thinking)
        extra_body["chat_template_kwargs"] = tmpl

        payload = {"model": model, "messages": chat_messages, **kwargs}
        self.calls.append(payload)
        self.call_counts[model] += 1

        response = self._client.chat.completions.create(
            model=model,
            messages=chat_messages,
            extra_body=extra_body,
            **kwargs,
        )
        usage = getattr(response, "usage", None)
        self.last_usage = {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        }
        message = response.choices[0].message
        content = message.content
        if content:
            return content.strip()
        # Fallback if a caller re-enabled thinking and content is empty.
        reasoning = getattr(message, "reasoning", None)
        return (reasoning or "").strip()
