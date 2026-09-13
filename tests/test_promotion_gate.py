from eval.promotion_gate import CorpusRegressionGate, retrieval_intent_accuracy


def test_retrieval_regression_gate_rejects_a_worse_corpus() -> None:
    evaluation = [{"question": "查台中機組尖峰出力", "intent": "unit_day"}]
    baseline = {"examples": [{"id": "good", "question": "台中機組尖峰出力", "intent": "unit_day"}]}
    proposed = {
        "examples": [
            *baseline["examples"],
            {"id": "bad", "question": "查台中機組尖峰出力", "intent": "other"},
        ]
    }
    gate = CorpusRegressionGate(baseline, evaluation)
    passed, metrics = gate(proposed)
    assert not passed
    assert metrics["baseline_retrieval_intent_accuracy"] == 1.0
    assert metrics["retrieval_intent_accuracy"] == 0.0


def test_empty_retrieval_evaluation_is_zero() -> None:
    assert retrieval_intent_accuracy({"examples": []}, []) == 0.0
