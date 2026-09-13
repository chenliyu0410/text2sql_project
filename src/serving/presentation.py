"""Build constrained explanations, statistics, and chart specifications from SQL rows."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

ALLOWED_CHART_KINDS = {"line", "bar", "scatter"}


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _numeric_indexes(columns: list[str], rows: list[list[object]]) -> list[int]:
    return [
        index
        for index, _column in enumerate(columns)
        if any(_is_number(row[index]) for row in rows if index < len(row))
    ]


def build_statistics(columns: list[str], rows: list[list[object]]) -> dict[str, Any]:
    statistics: dict[str, Any] = {"record_count": len(rows)}
    for index in _numeric_indexes(columns, rows):
        values = [float(row[index]) for row in rows if _is_number(row[index])]
        if values:
            statistics[columns[index]] = {
                "min": min(values),
                "max": max(values),
                "average": sum(values) / len(values),
            }
    return statistics


def build_chart_spec(columns: list[str], rows: list[list[object]]) -> dict[str, Any] | None:
    if len(rows) < 2 or not columns:
        return None
    numeric = _numeric_indexes(columns, rows)
    if not numeric:
        return None
    date_index = next(
        (index for index, column in enumerate(columns) if "日期" in column or "月份" in column),
        None,
    )
    category_index = next(
        (
            index
            for index, column in enumerate(columns)
            if index not in numeric and index != date_index
        ),
        None,
    )

    if date_index is not None:
        traces = []
        value_index = numeric[0]
        if category_index is not None:
            grouped: dict[str, list[list[object]]] = defaultdict(list)
            for row in rows:
                grouped[str(row[category_index])].append(row)
            for name, group_rows in sorted(grouped.items()):
                traces.append(
                    {
                        "type": "scatter",
                        "mode": "lines+markers",
                        "name": name,
                        "x": [row[date_index] for row in group_rows],
                        "y": [row[value_index] for row in group_rows],
                    }
                )
        else:
            for value_index in numeric:
                traces.append(
                    {
                        "type": "scatter",
                        "mode": "lines+markers",
                        "name": columns[value_index],
                        "x": [row[date_index] for row in rows],
                        "y": [row[value_index] for row in rows],
                    }
                )
        return {
            "kind": "line",
            "data": traces,
            "layout": {
                "title": {"text": "期間趨勢"},
                "xaxis": {"title": {"text": columns[date_index]}},
                "yaxis": {"title": {"text": columns[numeric[0]]}},
            },
        }

    if len(numeric) >= 2:
        left, right = numeric[:2]
        trace: dict[str, Any] = {
            "type": "scatter",
            "mode": "markers",
            "name": f"{columns[left]} / {columns[right]}",
            "x": [row[left] for row in rows],
            "y": [row[right] for row in rows],
        }
        if category_index is not None:
            trace["text"] = [row[category_index] for row in rows]
        return {
            "kind": "scatter",
            "data": [trace],
            "layout": {
                "title": {"text": "數值關係"},
                "xaxis": {"title": {"text": columns[left]}},
                "yaxis": {"title": {"text": columns[right]}},
            },
        }

    if category_index is not None:
        value_index = numeric[0]
        return {
            "kind": "bar",
            "data": [
                {
                    "type": "bar",
                    "name": columns[value_index],
                    "x": [row[category_index] for row in rows],
                    "y": [row[value_index] for row in rows],
                }
            ],
            "layout": {
                "title": {"text": "類別比較"},
                "xaxis": {"title": {"text": columns[category_index]}},
                "yaxis": {"title": {"text": columns[value_index]}},
            },
        }

    return None


def enrich_query_data(data: dict[str, Any]) -> dict[str, Any]:
    columns = [str(column) for column in data.get("columns", [])]
    rows = [list(row) for row in data.get("rows", [])]
    disclosures = data.get("disclosures", [])
    explanation = f"查詢完成，共取得 {len(rows)} 筆結果。"
    if disclosures:
        explanation += f" 其中有 {len(disclosures)} 項資料限制需一併閱讀。"
    return {
        **data,
        "chart_spec": build_chart_spec(columns, rows),
        "explanation": explanation,
        "statistics": build_statistics(columns, rows),
    }
