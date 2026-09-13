from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from text2sql.llm import OpenAILLM


def test_openai_adapter_uses_bounded_client_without_nested_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_options: dict[str, object] = {}
    request_options: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            request_options.update(kwargs)
            return SimpleNamespace(output_text='{"sql":"SELECT 1 LIMIT 1","params":[]}')

    class FakeOpenAI:
        def __init__(self, **kwargs: object):
            client_options.update(kwargs)
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    adapter = OpenAILLM(
        api_key="sk-test-timeout-only",
        model="test-model",
        timeout_seconds=7.5,
    )
    output = adapter.generate("test prompt")

    assert client_options == {
        "api_key": "sk-test-timeout-only",
        "timeout": 7.5,
        "max_retries": 0,
    }
    assert request_options["model"] == "test-model"
    assert request_options["store"] is False
    param_types = request_options["text"]["format"]["schema"]["properties"]["params"]["items"][
        "anyOf"
    ]
    assert param_types == [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "null"},
    ]
    assert output.startswith("{")


def test_openai_adapter_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        OpenAILLM(api_key="sk-test", timeout_seconds=0)
