"""Online and deterministic offline LLM adapters."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


class LLMProtocol(Protocol):
    def generate(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class GeneratedQuery:
    sql: str
    params: tuple[object, ...]


def parse_generated_query(output: str) -> GeneratedQuery:
    value = output.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1]).strip()
        if value.lower().startswith("sql\n"):
            value = value[4:]
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return GeneratedQuery(value, ())
    if not isinstance(payload, dict) or not isinstance(payload.get("sql"), str):
        raise ValueError("LLM 輸出必須含字串 sql 欄位。")
    params = payload.get("params", [])
    if not isinstance(params, list):
        raise ValueError("LLM params 必須是陣列。")
    return GeneratedQuery(payload["sql"].strip(), tuple(params))


class FakeLLM:
    def __init__(self, outputs: Iterable[str]):
        self._outputs = iter(outputs)
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        try:
            return next(self._outputs)
        except StopIteration as error:
            raise RuntimeError("FakeLLM 沒有更多預設輸出。") from error


class DisabledLLM:
    """Explicitly fail long-tail generation when online access is not configured."""

    def generate(self, prompt: str) -> str:
        del prompt
        raise RuntimeError("線上 LLM 未啟用；請設定 OPENAI_API_KEY 後重試。")


class OpenAILLM:
    def __init__(self, *, model: str | None = None, api_key: str | None = None):
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("缺少 OPENAI_API_KEY；線上查詢不會自動改用 FakeLLM。")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("請先執行 `uv sync --extra online`。") from error
        self.client = OpenAI(api_key=key)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

    def generate(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "text2sql_query",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string"},
                            "params": {"type": "array", "items": {}},
                        },
                        "required": ["sql", "params"],
                        "additionalProperties": False,
                    },
                }
            },
            store=False,
        )
        return response.output_text
