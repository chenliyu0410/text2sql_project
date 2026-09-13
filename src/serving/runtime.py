"""Construct the query runtime from repository configuration and SQLite metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ingest.validate import PROJECT_ROOT
from text2sql.db import ReadOnlySQLite
from text2sql.llm import DisabledLLM, OpenAILLM
from text2sql.pipeline import Text2SQLPipeline
from text2sql.semantic_guard import SemanticGuard
from text2sql.sql_guard import SqlGuard


@dataclass(frozen=True)
class ServiceRuntime:
    pipeline: Text2SQLPipeline
    executor: ReadOnlySQLite
    database: Path
    data_range: tuple[str, str]
    peak_columns: set[str]
    plants: set[str]
    online_llm: bool


def _yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} 必須是 YAML mapping。")
    return payload


def _single_column(executor: ReadOnlySQLite, sql: str) -> set[str]:
    _columns, rows = executor.execute(sql, ())
    return {str(row[0]) for row in rows}


def build_runtime(*, database: Path | None = None, root: Path = PROJECT_ROOT) -> ServiceRuntime:
    config = _yaml(root / "configs/config.yaml")
    guard_config = _yaml(root / "configs/guard.yaml")
    llm_config = _yaml(root / "configs/llm.yaml")
    retriever_config = _yaml(root / "configs/retriever.yaml")

    database = (database or root / config["paths"]["database"]).resolve()
    timeout = float(guard_config["sql"]["timeout_seconds"])
    executor = ReadOnlySQLite(database, timeout_seconds=timeout)
    peak_columns = _single_column(executor, 'SELECT DISTINCT "機組欄位" FROM v_peak LIMIT 200')
    plants = _single_column(executor, 'SELECT DISTINCT "電廠" FROM v_unit LIMIT 200')
    semantic_guard = SemanticGuard.from_database(database, peak_columns=peak_columns)

    online_llm = bool(os.getenv("OPENAI_API_KEY"))
    llm = OpenAILLM() if online_llm else DisabledLLM()
    ngram = retriever_config["character_ngram"]
    pipeline = Text2SQLPipeline(
        llm=llm,
        sql_guard=SqlGuard(max_rows=int(guard_config["sql"]["max_rows"])),
        run_sql=executor.execute,
        corpus_path=root / "corpus/training_corpus.json",
        data_range=semantic_guard.data_range,
        peak_columns=peak_columns,
        plants=plants,
        semantic_guard=semantic_guard,
        max_attempts=int(llm_config["max_attempts"]),
        top_k=int(retriever_config["top_k"]),
        ngram_min=int(ngram["min"]),
        ngram_max=int(ngram["max"]),
    )
    return ServiceRuntime(
        pipeline,
        executor,
        database,
        semantic_guard.data_range,
        peak_columns,
        plants,
        online_llm,
    )
