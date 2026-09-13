"""Atomic staging, validation, promotion, and rollback for retrieval examples."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from text2sql.corpus import build_index, corpus_checksum, load_corpus, normalize_question

Validator = Callable[[str, str], tuple[bool, str]]
RegressionGate = Callable[[dict[str, Any]], tuple[bool, dict[str, float]]]


@dataclass(frozen=True)
class CorpusCandidate:
    id: str
    question: str
    sql: str
    source: str
    created_at: str
    approved_by: str
    schema_version: str
    data_manifest_version: str
    outcome: str
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionResult:
    promoted: bool
    version: str | None
    rejected: tuple[dict[str, str], ...]
    metrics: dict[str, float]


EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"\b(?:sk|sess|token)-[A-Za-z0-9_-]{8,}\b")
ACCOUNT_PATTERN = re.compile(r"(?<!\d)\d{10,16}(?!\d)")


def deidentify(value: str) -> str:
    value = EMAIL_PATTERN.sub("[EMAIL]", value)
    value = TOKEN_PATTERN.sub("[TOKEN]", value)
    return ACCOUNT_PATTERN.sub("[ACCOUNT]", value)


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _candidate_example(candidate: CorpusCandidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "question": deidentify(candidate.question),
        "sql": candidate.sql.strip(),
        "intent": candidate.validation.get("intent", "other"),
        "metadata": {
            key: value
            for key, value in asdict(candidate).items()
            if key not in {"id", "question", "sql", "validation"}
        },
    }


def promote_batch(
    candidates: Iterable[CorpusCandidate],
    *,
    corpus_path: Path,
    index_path: Path,
    versions_dir: Path,
    benchmark_question_set: set[str],
    sql_validator: Validator,
    semantic_validator: Validator,
    result_validator: Validator,
    regression_gate: RegressionGate,
) -> PromotionResult:
    """Promote all candidates or none; a failed batch never changes published files."""
    corpus = load_corpus(corpus_path)
    existing_questions = {normalize_question(example["question"]) for example in corpus["examples"]}
    batch_questions: set[str] = set()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for candidate in candidates:
        reason = ""
        question = deidentify(candidate.question)
        normalized = normalize_question(question)
        if candidate.outcome not in {"success", "corrected"}:
            reason = "ineligible_outcome"
        elif not candidate.approved_by.strip():
            reason = "missing_approval"
        elif normalized in existing_questions or normalized in batch_questions:
            reason = "duplicate_question"
        elif normalized in benchmark_question_set:
            reason = "benchmark_leakage"
        else:
            for validator in (sql_validator, semantic_validator, result_validator):
                passed, detail = validator(question, candidate.sql)
                if not passed:
                    reason = detail
                    break
        if reason:
            rejected.append({"id": candidate.id, "reason": reason})
            continue
        batch_questions.add(normalized)
        accepted.append(_candidate_example(candidate))

    if rejected:
        return PromotionResult(False, None, tuple(rejected), {})

    proposed = {**corpus, "examples": [*corpus["examples"], *accepted]}
    proposed_checksum = corpus_checksum(proposed)
    proposed["version"] = f"corpus-{proposed_checksum[:12]}"
    passed, metrics = regression_gate(proposed)
    if not passed:
        return PromotionResult(
            False,
            None,
            ({"id": "batch", "reason": "regression_gate_failed"},),
            metrics,
        )

    old_checksum = corpus_checksum(corpus)
    backup_path = versions_dir / f"{corpus['version']}-{old_checksum[:12]}.json"
    if not backup_path.exists():
        _atomic_json_write(backup_path, corpus)
    _atomic_json_write(corpus_path, proposed)
    _atomic_json_write(index_path, build_index(proposed))
    return PromotionResult(True, proposed["version"], (), metrics)


def rollback_corpus(*, corpus_path: Path, index_path: Path, backup_path: Path) -> str:
    corpus = load_corpus(backup_path)
    _atomic_json_write(corpus_path, corpus)
    _atomic_json_write(index_path, build_index(corpus))
    return hashlib.sha256(corpus_path.read_bytes()).hexdigest()
