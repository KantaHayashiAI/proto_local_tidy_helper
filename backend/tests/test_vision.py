from __future__ import annotations

import json
from pathlib import Path

import pytest

from tidy_helper.app.services.vision import (
    OpenAICompatibleVisionProvider,
    OpenAICompatibleResponsesVisionProvider,
    PreferResponsesVisionProvider,
    ResponsesUnsupportedError,
    VisionProvider,
)


class StubProvider(VisionProvider):
    def __init__(self, name: str, model_name: str, result: object = None, error: Exception | None = None):
        super().__init__(name, model_name)
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def analyze_scene(self, **kwargs):  # type: ignore[override]
        self.calls.append(("analyze_scene", kwargs))
        if self.error:
            raise self.error
        return self.result

    def check_completion(self, **kwargs):  # type: ignore[override]
        self.calls.append(("check_completion", kwargs))
        if self.error:
            raise self.error
        return self.result

    def healthcheck(self) -> dict[str, object]:
        return {"ok": True}


def make_responses_provider() -> OpenAICompatibleResponsesVisionProvider:
    return OpenAICompatibleResponsesVisionProvider(
        provider_name="local",
        base_url="http://127.0.0.1:1234/v1",
        model_name="qwen/qwen3.5-9b",
    )


def make_chat_provider() -> OpenAICompatibleVisionProvider:
    return OpenAICompatibleVisionProvider(
        provider_name="local",
        base_url="http://127.0.0.1:1234/v1",
        model_name="qwen/qwen3.5-9b",
    )


def test_parse_json_strips_code_fence():
    provider = make_responses_provider()
    raw = """
```json
{
  "ok": true
}
```
"""
    assert provider._parse_json(raw) == {"ok": True}


def test_chat_parse_json_extracts_payload_after_think_block():
    provider = make_chat_provider()
    raw = """
<think>
Need to inspect the workspace first.
</think>
{
  "ok": true
}
"""
    assert provider._parse_json(raw) == {"ok": True}


def test_chat_parse_json_extracts_json_fragment_from_prose():
    provider = make_chat_provider()
    raw = 'Here is the result: {"ok": true, "tasks": []} End.'
    assert provider._parse_json(raw) == {"ok": True, "tasks": []}


def test_responses_parse_json_does_not_recover_from_think_blocks():
    provider = make_responses_provider()
    raw = """
<think>
Need to inspect the workspace first.
</think>
{
  "ok": true
}
"""
    with pytest.raises(json.JSONDecodeError):
        provider._parse_json(raw)


def test_prefer_responses_provider_falls_back_only_on_unsupported():
    primary = StubProvider(
        "local",
        "qwen/qwen3.5-9b",
        error=ResponsesUnsupportedError("responses unsupported"),
    )
    fallback = StubProvider("local", "qwen/qwen3.5-9b", result={"status": "fallback"})
    provider = PreferResponsesVisionProvider(primary=primary, fallback=fallback)  # type: ignore[arg-type]

    result = provider.check_completion(
        image_path=Path("image.png"),
        task={"title": "tidy"},
        reference_summary=None,
    )

    assert result == {"status": "fallback"}
    assert [call[0] for call in primary.calls] == ["check_completion"]
    assert [call[0] for call in fallback.calls] == ["check_completion"]


def test_prefer_responses_provider_keeps_primary_on_success():
    primary = StubProvider("local", "qwen/qwen3.5-9b", result={"status": "primary"})
    fallback = StubProvider("local", "qwen/qwen3.5-9b", result={"status": "fallback"})
    provider = PreferResponsesVisionProvider(primary=primary, fallback=fallback)  # type: ignore[arg-type]

    result = provider.analyze_scene(
        image_path=Path("image.png"),
        recent_history=[],
        active_tasks=[],
        rules=[],
        quiet_hours_active=False,
        notifications_today=0,
    )

    assert result == {"status": "primary"}
    assert [call[0] for call in primary.calls] == ["analyze_scene"]
    assert fallback.calls == []
