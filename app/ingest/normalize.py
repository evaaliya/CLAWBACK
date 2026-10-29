"""Merchant normalization via Nano (FakeLLM in tests / recorded mode)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.clock import Clock
from app.privacy.redact import scrub_for_model
from app.privacy.trace import complete_traced


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
    conn: sqlite3.Connection | None = None,
    clock: Clock | None = None,
) -> NormalizeResult:
    """Ask Nano for a normalized merchant name and category."""
    safe_desc = scrub_for_model(merchant_raw)
    prompt = (
        "Normalize this bank-statement merchant description. "
        "Return JSON with keys merchant_norm and category "
        "(subscription|purchase|other). "
        f"Description: {safe_desc}"
    )
    raw = _complete(
        llm,
        conn=conn,
        clock=clock,
        model=model,
        prompt=prompt,
        recording_key=f"normalize:{merchant_raw}",
    )
    data = _as_dict(raw)
    try:
        return NormalizeResult.model_validate(data)
    except ValidationError:
        # One retry with the validation error, same as receipt flow.
        raw2 = _complete(
            llm,
            conn=conn,
            clock=clock,
            model=model,
            prompt=(
                f"{prompt}\nPrevious output failed validation. "
                "Reply with valid JSON only."
            ),
            recording_key=f"normalize:{merchant_raw}",
        )
        return NormalizeResult.model_validate(_as_dict(raw2))


def _complete(
    llm: LLMClient,
    *,
    conn: sqlite3.Connection | None,
    clock: Clock | None,
    model: str,
    prompt: str,
    recording_key: str,
) -> Any:
    if conn is not None and clock is not None:
        return complete_traced(
            conn,
            clock,
            llm,
            role="normalize",
            model=model,
            prompt=prompt,
            recording_key=recording_key,
        )
    return llm.complete(model=model, prompt=prompt, recording_key=recording_key)


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise TypeError(f"unexpected LLM response type: {type(raw).__name__}")
