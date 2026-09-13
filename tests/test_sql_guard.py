import json
from pathlib import Path

import pytest

from text2sql.sql_guard import SqlGuard

ROOT = Path(__file__).parents[1]


def test_all_attack_benchmark_queries_are_blocked() -> None:
    attacks = json.loads(
        (ROOT / "benchmarks" / "attack_questions.json").read_text(encoding="utf-8")
    )
    guard = SqlGuard()
    results = {item["id"]: guard.validate(item["input"]) for item in attacks}
    assert len(results) == 15
    assert all(not result.allowed for result in results.values())


@pytest.mark.parametrize(
    ("sql", "params", "code"),
    [
        ('SELECT "不存在" FROM v_peak LIMIT 1', (), "SQL_COLUMN_NOT_ALLOWED"),
        ('SELECT "日期" FROM v_peak WHERE "機組欄位" = ? LIMIT 1', (), "SQL_PARAMETER_MISMATCH"),
        ('SELECT "日期" FROM v_peak LIMIT 201', (), "SQL_LIMIT_EXCEEDED"),
        (
            "SELECT load_extension(?) FROM v_peak LIMIT 1",
            ("evil",),
            "SQL_FUNCTION_NOT_ALLOWED",
        ),
        (
            'SELECT "日期" FROM v_peak WHERE "機組欄位" = \'台中#1\' LIMIT 1',
            (),
            "SQL_LITERAL_NOT_PARAMETERIZED",
        ),
    ],
)
def test_guard_rejects_specific_unsafe_shapes(
    sql: str, params: tuple[object, ...], code: str
) -> None:
    result = SqlGuard().validate(sql, params)
    assert not result.allowed
    assert result.code == code


def test_guard_accepts_parameterized_view_query() -> None:
    sql = (
        'SELECT "日期", "尖峰出力_萬瓩" FROM v_peak '
        'WHERE "機組欄位" = ? ORDER BY "日期" DESC LIMIT 20'
    )
    result = SqlGuard().validate(sql, ("台中#1",))
    assert result.allowed
    assert result.tables == ("v_peak",)
