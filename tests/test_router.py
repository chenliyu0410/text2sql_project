import json
from pathlib import Path

from text2sql.entities import extract_entities
from text2sql.router import classify_intent, route

ROOT = Path(__file__).parents[1]


def test_golden_intent_accuracy_is_at_least_ninety_percent() -> None:
    questions = json.loads(
        (ROOT / "benchmarks" / "golden_questions.json").read_text(encoding="utf-8")
    )
    correct = sum(classify_intent(item["question"]) == item["intent"] for item in questions)
    assert correct / len(questions) >= 0.90


def test_system_metric_route_is_parameterized() -> None:
    question = "2026年7月備轉容量率最低是哪一天"
    routed = route(question, extract_entities(question), peak_columns=set())
    assert routed.intent == "system_metric"
    assert routed.params == ("2026-07-01", "2026-07-31")
    assert routed.sql and routed.sql.count("?") == 2
    assert "ASC LIMIT 1" in routed.sql


def test_unit_day_route_uses_alias_and_chinese_date() -> None:
    question = "2026年五月二日台中2號機尖峰時輸出多少"
    routed = route(question, extract_entities(question), peak_columns={"台中#2"})
    assert routed.intent == "unit_day"
    assert routed.params == ("台中#2", "2026-05-02")
    assert routed.sql and "LIMIT 1" in routed.sql
