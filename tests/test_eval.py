from pathlib import Path

import pytest

from eval.metrics import QueryResult, accuracy, grouped_accuracy, result_match
from eval.run_eval import run_evaluation
from ingest.build_db import build_database
from ingest.validate import PROJECT_ROOT


def test_result_match_uses_column_and_row_sets_not_order() -> None:
    left = QueryResult(("date", "value"), (("2026-01-02", 2), ("2026-01-01", 1)))
    right = QueryResult(("value", "date"), ((1, "2026-01-01"), (2, "2026-01-02")))
    assert result_match(left, right)
    assert not result_match(left, QueryResult(("date", "other"), left.rows))


def test_metrics_report_counts_and_groups() -> None:
    assert accuracy([True, False, True]) == {"passed": 2, "total": 3, "accuracy": 2 / 3}
    outcomes = [
        {"split": "in", "passed": True},
        {"split": "out", "passed": False},
        {"split": "out", "passed": True},
    ]
    assert grouped_accuracy(outcomes, group_key="split")["out"]["accuracy"] == 0.5


@pytest.mark.integration
def test_complete_offline_evaluation_meets_acceptance(tmp_path: Path) -> None:
    database = tmp_path / "power.db"
    build_database(database)
    report = run_evaluation(
        database=database,
        benchmark_dir=PROJECT_ROOT / "benchmarks",
        corpus_path=PROJECT_ROOT / "corpus/training_corpus.json",
    )
    assert report["status"] == "pass"
    assert report["execution"]["by_corpus_split"]["false"]["accuracy"] >= 0.60
    assert report["safety"]["semantic_false_positives"]["rate"] <= 0.05
    assert set(report["ablation"]) == {"rag", "semantic_guard", "max_attempts", "routing"}
