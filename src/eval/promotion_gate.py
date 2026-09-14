"""Regression gate used before an updated retrieval corpus is published."""

from __future__ import annotations

from typing import Any

from text2sql.retriever import TfidfRetriever


def retrieval_intent_accuracy(
    corpus: dict[str, Any], evaluation_items: list[dict[str, Any]]
) -> float:
    retriever = TfidfRetriever(corpus["examples"])
    passed = 0
    for item in evaluation_items:
        matches = retriever.retrieve(item["question"], top_k=1)
        predicted = matches[0].example["intent"] if matches else "other"
        passed += predicted == item["intent"]
    return passed / len(evaluation_items) if evaluation_items else 0.0


class CorpusRegressionGate:
    """Reject corpus updates whose retrieval intent score regresses beyond tolerance."""

    def __init__(
        self,
        baseline_corpus: dict[str, Any],
        evaluation_items: list[dict[str, Any]],
        *,
        maximum_drop: float = 0.0,
    ):
        if not 0 <= maximum_drop <= 1:
            raise ValueError("maximum_drop 必須介於 0 與 1。")
        self.evaluation_items = evaluation_items
        self.maximum_drop = maximum_drop
        self.baseline = retrieval_intent_accuracy(baseline_corpus, evaluation_items)

    def __call__(self, proposed_corpus: dict[str, Any]) -> tuple[bool, dict[str, float]]:
        proposed = retrieval_intent_accuracy(proposed_corpus, self.evaluation_items)
        floor = self.baseline - self.maximum_drop
        return proposed >= floor, {
            "retrieval_intent_accuracy": proposed,
            "baseline_retrieval_intent_accuracy": self.baseline,
            "minimum_allowed_accuracy": floor,
        }
