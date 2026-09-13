from __future__ import annotations

import json
from pathlib import Path

from text2sql.corpus import load_corpus, normalize_question
from text2sql.corpus_builder import (
    CorpusCandidate,
    deidentify,
    promote_batch,
    rollback_corpus,
)


def _write_corpus(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "corpus-v1",
                "ddl": [],
                "documentation": [],
                "examples": [
                    {
                        "id": "base",
                        "question": "2026年7月最高尖峰負載日",
                        "sql": "SELECT 1 LIMIT 1",
                        "intent": "system_metric",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _candidate(**overrides: str) -> CorpusCandidate:
    values = {
        "id": "candidate-1",
        "question": "林口1號機在2026年最高出力",
        "sql": 'SELECT MAX("尖峰出力_萬瓩") FROM v_peak LIMIT 1',
        "source": "corrected",
        "created_at": "2026-09-13T00:00:00Z",
        "approved_by": "reviewer",
        "schema_version": "1",
        "data_manifest_version": "fixture",
        "outcome": "corrected",
    }
    values.update(overrides)
    return CorpusCandidate(**values)


def _pass(_question: str, _sql: str) -> tuple[bool, str]:
    return True, ""


def _regression(_corpus: dict[str, object]) -> tuple[bool, dict[str, float]]:
    return True, {"execution_accuracy": 1.0}


def test_deidentify_removes_email_token_and_long_account_number() -> None:
    value = "a@example.com sk-secret123 123456789012"
    assert deidentify(value) == "[EMAIL] [TOKEN] [ACCOUNT]"


def test_failed_batch_does_not_publish_partial_examples(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.json"
    index_path = tmp_path / "index.json"
    _write_corpus(corpus_path)
    before = corpus_path.read_bytes()

    result = promote_batch(
        [_candidate(), _candidate(id="bad", outcome="failed", question="另一題")],
        corpus_path=corpus_path,
        index_path=index_path,
        versions_dir=tmp_path / "versions",
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )

    assert result.promoted is False
    assert corpus_path.read_bytes() == before
    assert not index_path.exists()


def test_promotion_versions_and_rollback_are_atomic(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.json"
    index_path = tmp_path / "index.json"
    versions = tmp_path / "versions"
    _write_corpus(corpus_path)

    result = promote_batch(
        [_candidate()],
        corpus_path=corpus_path,
        index_path=index_path,
        versions_dir=versions,
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )

    assert result.promoted is True
    assert len(load_corpus(corpus_path)["examples"]) == 2
    backup = next(versions.glob("*.json"))
    rollback_corpus(corpus_path=corpus_path, index_path=index_path, backup_path=backup)
    assert len(load_corpus(corpus_path)["examples"]) == 1


def test_benchmark_question_is_rejected(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.json"
    _write_corpus(corpus_path)
    candidate = _candidate()

    result = promote_batch(
        [candidate],
        corpus_path=corpus_path,
        index_path=tmp_path / "index.json",
        versions_dir=tmp_path / "versions",
        benchmark_question_set={normalize_question(candidate.question)},
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )

    assert result.rejected == ({"id": "candidate-1", "reason": "benchmark_leakage"},)
