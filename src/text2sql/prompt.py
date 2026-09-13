"""Prompt assembly with explicit schema, rules, data range, and retrieved examples."""

from __future__ import annotations

import json
from typing import Any

from text2sql.retriever import RetrievedExample


def build_prompt(
    question: str,
    *,
    corpus: dict[str, Any],
    examples: list[RetrievedExample],
    data_range: tuple[str, str],
    prior_error: str | None = None,
) -> str:
    payload = {
        "task": "將問題轉成 SQLite 單一 SELECT，只查 v_* view，使用 ? placeholder，並加上 LIMIT。",
        "output": {"sql": "string", "params": ["JSON scalar"]},
        "data_range": {"start": data_range[0], "end": data_range[1]},
        "ddl": corpus["ddl"],
        "rules": corpus["documentation"],
        "examples": [item.example for item in examples],
        "question": question,
    }
    if prior_error:
        payload["previous_attempt_error"] = prior_error
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
