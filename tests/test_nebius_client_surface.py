"""NebiusLLM matches FakeLLM.complete surface; no live network in tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.llm.factory import build_llm, resolve_model_ids
from app.llm.nebius import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_NANO,
    DEFAULT_MODEL_SUPER,
    DEFAULT_MODEL_ULTRA,
    NebiusLLM,
)
from app.config import Settings


def test_nebius_client_surface(monkeypatch) -> None:
    fake_create = MagicMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ok":true}', reasoning=None)
                )
            ]
        )
    )
    fake_openai = MagicMock()
    fake_openai.return_value.chat.completions.create = fake_create
    monkeypatch.setattr("app.llm.nebius.OpenAI", fake_openai)

    llm = NebiusLLM(api_key="test-key", base_url=DEFAULT_BASE_URL)
    out = llm.complete(
        model=DEFAULT_MODEL_NANO,
        prompt="Normalize merchant X",
        recording_key="normalize:X",
    )
    assert out == '{"ok":true}'
    assert llm.call_counts[DEFAULT_MODEL_NANO] == 1
    assert llm.ultra_calls == 0

    kwargs = fake_create.call_args.kwargs
    assert kwargs["model"] == DEFAULT_MODEL_NANO
    assert kwargs["messages"] == [{"role": "user", "content": "Normalize merchant X"}]
    assert "recording_key" not in kwargs
    assert kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False

    settings = Settings(
        nebius_api_key="",
        recorded_mode=False,
    )
    assert isinstance(build_llm(settings), type(build_llm(Settings(recorded_mode=True))))

    ids = resolve_model_ids(Settings())
    assert ids["nano"] == DEFAULT_MODEL_NANO
    assert ids["super"] == DEFAULT_MODEL_SUPER
    assert ids["ultra"] == DEFAULT_MODEL_ULTRA
