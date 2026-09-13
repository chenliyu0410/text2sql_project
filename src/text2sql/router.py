"""Priority-ordered intent routing and zero-cost parameterized handlers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from text2sql.aliases import resolve_peak_column
from text2sql.entities import Entities


@dataclass(frozen=True)
class RoutedQuery:
    intent: str
    sql: str | None = None
    params: tuple[object, ...] = ()


def classify_intent(question: str) -> str:
    question = re.sub(r"\s+", "", question)
    system_words = ("負載", "備轉", "供電能力", "工業用電", "民生用電", "系統指標")

    # Composite/report requests intentionally stay on the long-tail LLM path.
    if (
        any(word in question for word in ("散點", "容量缺口", "資料可用日期", "系統摘要", "各類別"))
        or ("負載" in question and "備轉" in question)
        or ("每月平均" in question and "備轉" in question)
        or ("工業" in question and "民生" in question)
    ):
        return "other"

    plant_words = ("機組", "設備", "各機", "所屬", "機組名稱", "機組主檔")
    if ("電廠" in question or "廠" in question) and any(word in question for word in plant_words):
        return "plant_units"

    fuel_words = ("燃料", "煤機", "燃煤", "水力", "天然氣", "燃氣", "重油", "輕柴油")
    statistic_words = (
        "容量",
        "幾台",
        "台數",
        "數量",
        "最多",
        "統計",
        "排行",
        "平均",
        "合計",
    )
    if any(word in question for word in fuel_words) and any(
        word in question for word in statistic_words
    ):
        return "fuel_stats"

    if (
        any(word in question for word in ("歲修", "維修", "修復", "維修中"))
        or "停機事件" in question
    ):
        return "outage"

    comparison_shape = any(
        word in question for word in ("比較", "誰高", "兩台機組", "兩個彙總", "指定兩台")
    ) or (
        any(word in question for word in ("和", "與", "及"))
        and any(word in question for word in ("曲線", "峰值", "平均", "趨勢", "最大值", "輸出"))
    )
    if comparison_shape:
        return "comparison"

    if any(
        word in question
        for word in ("前三", "前五", "前十", "排行", "排序", "名次", "由高到低", "由小到大")
    ) or re.search(
        r"(?:最大|最小|最高|最低)(?:的)?[0-9一二三四五六七八九十]+(?:名|欄|個)", question
    ):
        return "daily_ranking"

    day_count_words = ("幾天", "日數", "天數", "日期數", "的天", "的日期")
    zero_state = ("零出力" in question and "非零出力" not in question) or any(
        word in question for word in ("零輸出", "零值", "沒有出力", "沒發電", "等於零")
    )
    if zero_state or (
        any(word in question for word in day_count_words)
        and any(word in question for word in ("有出力", "有發電", "有值", "非零", "停機"))
    ):
        return "zero_days"

    if any(word in question for word in system_words):
        return "system_metric"

    explicit_day = bool(
        re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", question)
        or re.search(
            r"(?:20\d{2}年|今年|去年)?[0-9一二三四五六七八九十]+月[0-9一二三四五六七八九十]+日",
            question,
        )
        or any(word in question for word in ("某天", "指定日期", "指定日", "同一天"))
    )
    unit_shape = any(
        word in question
        for word in ("機組", "號機", "德基", "青山", "大林", "林口", "台中", "大觀", "興達")
    )
    if explicit_day and unit_shape:
        return "unit_day"

    if any(word in question for word in ("最高", "最低", "最大", "最小", "峰值", "極值")):
        return "unit_extreme"
    return "other"


def route(question: str, entities: Entities, *, peak_columns: set[str]) -> RoutedQuery:
    intent = classify_intent(question)
    if intent == "system_metric" and entities.date_range:
        metric = next(
            (
                name
                for word, name in (
                    ("備轉容量率", "備轉容量率_pct"),
                    ("備轉容量", "備轉容量_萬瓩"),
                    ("淨尖峰供電能力", "淨尖峰供電能力_萬瓩"),
                    ("尖峰負載", "尖峰負載_萬瓩"),
                    ("民生用電", "民生用電_百萬度"),
                    ("工業用電", "工業用電_百萬度"),
                )
                if word in question
            ),
            None,
        )
        if metric and any(word in question for word in ("最低", "最小", "最高", "最大")):
            direction = "ASC" if any(word in question for word in ("最低", "最小")) else "DESC"
            return RoutedQuery(
                intent,
                f'SELECT "日期", "{metric}" FROM v_system '
                f'WHERE "日期" BETWEEN ? AND ? ORDER BY "{metric}" {direction} LIMIT 1',
                (entities.date_range.start, entities.date_range.end),
            )
    if intent == "unit_day" and entities.explicit_date:
        resolution = resolve_peak_column(question, peak_columns)
        if resolution.value:
            return RoutedQuery(
                intent,
                'SELECT "日期", "機組欄位", "尖峰出力_萬瓩" FROM v_peak '
                'WHERE "機組欄位" = ? AND "日期" = ? LIMIT 1',
                (resolution.value, entities.explicit_date),
            )
    return RoutedQuery(intent)
