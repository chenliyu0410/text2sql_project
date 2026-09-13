import csv
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from align.crosswalk import parse_crosswalk
from align.pitfalls import generate_pitfalls
from text2sql.entities import extract_entities
from text2sql.llm import GeneratedQuery
from text2sql.semantic_guard import SemanticGuard, load_semantic_context

ROOT = Path(__file__).parents[1]
DATA_RANGE = ("2025-01-01", "2026-07-31")
PEAK_COLUMNS = {"興達#3", "興達 (#1-#5)", "台中#1", "立霧"}


@pytest.fixture(scope="module")
def semantic_guard() -> SemanticGuard:
    with (ROOT / "taipower_align" / "crosswalk.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        pitfalls = generate_pitfalls(parse_crosswalk(csv.DictReader(handle)), ratio_max=1.06)
    return SemanticGuard(data_range=DATA_RANGE, peak_columns=PEAK_COLUMNS, pitfalls=pitfalls)


def test_trap_benchmark_hit_rate_is_at_least_ninety_five_percent(
    semantic_guard: SemanticGuard,
) -> None:
    traps = json.loads((ROOT / "benchmarks" / "trap_questions.json").read_text(encoding="utf-8"))
    hits = 0
    for item in traps:
        entities = extract_entities(item["question"], reference_date=date(2026, 7, 31))
        decision = semantic_guard.check_question(item["question"], entities)
        hits += (decision.code, decision.severity) == (
            item["expect"]["code"],
            item["expect"]["severity"],
        )
    assert hits / len(traps) >= 0.95


def test_safe_question_false_positive_rate_is_at_most_five_percent(
    semantic_guard: SemanticGuard,
) -> None:
    safe = (
        "2026年7月20日全部機組尖峰出力合計",
        "2025年台中#1平均尖峰出力",
        "台中#1裝置容量_萬瓩與尖峰出力_萬瓩比值",
        "水力機組總裝置容量",
        "風力彙總尖峰出力",
        "其他小水力2026年7月20日出力",
        "氣渦輪單日尖峰出力",
        "台中發電廠具名機組清單",
        "查台中發電廠台中#1的出力",
        "大潭2025年最高出力",
        "大林#1歲修排程",
        "立霧2025年零出力幾天",
        "台中#1在2025年沒有出力的日數",
        "興達4號機2025年最高出力",
        "興達複循環彙總六月出力",
        "2025年1月1日系統尖峰負載",
        "2026年7月31日備轉容量率",
        "同一天所有機組尖峰出力合計",
        "各燃料裝置容量瓩總和",
        "2026年6月尖峰出力萬瓩平均",
    )
    blocked = 0
    for question in safe:
        entities = extract_entities(question, reference_date=date(2026, 7, 31))
        decision = semantic_guard.check_question(question, entities)
        blocked += decision.severity in {"refuse", "clarify", "disclose"}
    assert blocked / len(safe) <= 0.05


def test_sql_shape_blocks_cross_date_sum_but_allows_same_day(
    semantic_guard: SemanticGuard,
) -> None:
    sql = 'SELECT SUM("尖峰出力_萬瓩") FROM v_peak LIMIT 1'
    blocked = semantic_guard.check_sql(
        "查尖峰出力統計", GeneratedQuery(sql, ()), extract_entities("查尖峰出力統計")
    )
    assert (blocked.code, blocked.severity) == ("PEAK_SUM_ACROSS_DAYS", "refuse")

    question = "2026年7月20日全部機組尖峰出力合計"
    allowed = semantic_guard.check_sql(
        question, GeneratedQuery(sql, ()), extract_entities(question)
    )
    assert allowed.code == "OK"


def test_sql_shape_detects_unit_mismatch(semantic_guard: SemanticGuard) -> None:
    query = GeneratedQuery('SELECT "裝置容量_瓩" / "尖峰出力_萬瓩" FROM v_peak LIMIT 1', ())
    decision = semantic_guard.check_sql("比率", query, extract_entities("比率"))
    assert (decision.code, decision.severity) == ("UNIT_MISMATCH", "refuse")


def test_sql_shape_discloses_unbounded_zero_filter(semantic_guard: SemanticGuard) -> None:
    query = GeneratedQuery('SELECT COUNT(*) FROM v_peak WHERE "尖峰出力_萬瓩" = 0 LIMIT 1', ())
    decision = semantic_guard.check_sql("統計", query, extract_entities("統計"))
    assert (decision.code, decision.severity) == ("ZERO_PERIOD_AMBIGUOUS", "disclose")


@pytest.mark.parametrize(
    ("question", "query", "expected"),
    [
        (
            "查類別資料",
            GeneratedQuery('SELECT "機組名" FROM v_unit WHERE "燃料" = ? LIMIT 20', ("風力",)),
            ("NO_UNIT_DETAIL", "refuse"),
        ),
        (
            "長期趨勢",
            GeneratedQuery(
                'SELECT "日期", "尖峰出力_萬瓩" FROM v_peak '
                'WHERE "是殘差欄" = 1 ORDER BY "日期" LIMIT 100',
                (),
            ),
            ("RESIDUAL_TREND", "refuse"),
        ),
        (
            "各廠總計",
            GeneratedQuery(
                'SELECT "電廠", SUM("裝置容量_萬瓩") FROM v_unit GROUP BY "電廠" LIMIT 30',
                (),
            ),
            ("PLANT_TOTAL_INCOMPLETE", "disclose"),
        ),
        (
            "容量對帳",
            GeneratedQuery(
                'SELECT "機組欄位", "對應裝置容量_萬瓩" FROM v_peak WHERE "機組欄位" = ? LIMIT 1',
                ("大潭 (#1-#9)",),
            ),
            ("KNOWN_CAPACITY_GAP", "disclose"),
        ),
    ],
)
def test_additional_sql_shapes(
    semantic_guard: SemanticGuard,
    question: str,
    query: GeneratedQuery,
    expected: tuple[str, str],
) -> None:
    decision = semantic_guard.check_sql(question, query, extract_entities(question))
    assert (decision.code, decision.severity) == expected


def test_context_is_loaded_from_database(tmp_path) -> None:
    database = tmp_path / "context.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE meta_manifest (id INTEGER, data_start TEXT, data_end TEXT)"
        )
        connection.execute("INSERT INTO meta_manifest VALUES (1, '2025-01-01', '2026-07-31')")
        connection.execute(
            """CREATE TABLE meta_pitfall (
                   id INTEGER, pitfall_code TEXT, target_kind TEXT, target_name TEXT,
                   severity TEXT, reason TEXT, suggestion TEXT, evidence TEXT)"""
        )
        connection.execute(
            "INSERT INTO meta_pitfall VALUES (1, 'RESIDUAL_TREND', 'column', ?, "
            "'refuse', 'reason', 'suggestion', '{}')",
            ("氣渦輪",),
        )
    data_range, pitfalls = load_semantic_context(database)
    assert data_range == DATA_RANGE
    assert pitfalls[0].target_name == "氣渦輪"
