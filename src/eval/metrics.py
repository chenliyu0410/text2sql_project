"""Result-set and classification metrics with no SQL-string comparison."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


def canonical_result(result: QueryResult) -> tuple[tuple[str, ...], frozenset[tuple[Any, ...]]]:
    """Normalize column order and row order while retaining column identity."""

    if len(result.columns) != len(set(result.columns)):
        raise ValueError("結果欄名必須唯一，才能比較等價性。")
    indexes = sorted(range(len(result.columns)), key=result.columns.__getitem__)
    columns = tuple(result.columns[index] for index in indexes)
    rows = frozenset(tuple(row[index] for index in indexes) for row in result.rows)
    return columns, rows


def result_match(left: QueryResult, right: QueryResult) -> bool:
    return canonical_result(left) == canonical_result(right)


def accuracy(values: Iterable[bool]) -> dict[str, int | float]:
    values = tuple(values)
    passed = sum(values)
    total = len(values)
    return {"passed": passed, "total": total, "accuracy": passed / total if total else 0.0}


def grouped_accuracy(
    outcomes: Sequence[dict[str, Any]], *, group_key: str, result_key: str = "passed"
) -> dict[str, dict[str, int | float]]:
    groups: dict[str, list[bool]] = {}
    for outcome in outcomes:
        groups.setdefault(str(outcome[group_key]).lower(), []).append(bool(outcome[result_key]))
    return {name: accuracy(values) for name, values in sorted(groups.items())}
