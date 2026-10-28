"""Merchant normalization via Nano (FakeLLM in tests / recorded mode)."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError


class NormalizeResult(BaseModel):
    merchant_norm: str
    category: str = Field(pattern="^(subscription|purchase|other)$")


class LLMClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]] | None = None,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> Any: ...


def normalize_merchant(
    llm: LLMClient,
    merchant_raw: str,
    *,
    model: str = "nano",
) -> NormalizeResult:
    """Ask Nano for a normalized merchant name and category."""
    prompt = (
        "Normalize this bank-statement merchant description. "
        "Return JSON with keys merchant_norm and category "
        "(subscription|purchase|other). "
        f"Description: {merchant_raw}"
    )
    raw = llm.complete(
        model=model,
        prompt=prompt,
        recording_key=f"normalize:{merchant_raw}",
    )
    data = _as_dict(raw)
    try:
        return NormalizeResult.model_validate(data)
    except ValidationError:
        # One retry with the validation error, same as receipt flow.
        raw2 = llm.complete(
            model=model,
            prompt=f"{prompt}\nPrevious output failed validation. Reply with valid JSON only.",
            recording_key=f"normalize:{merchant_raw}",
        )
        return NormalizeResult.model_validate(_as_dict(raw2))


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise TypeError(f"unexpected LLM response type: {type(raw).__name__}")
