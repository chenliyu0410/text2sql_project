"""Align d006008 outage names to the unit master without database or network I/O."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from align.naming import normalize_name, outage_unit_candidates


@dataclass(frozen=True)
class OutageAlignment:
    source_name: str
    unit_name: str | None
    plant_name: str | None
    status: str
    candidates: tuple[str, ...]


def align_outage_name(
    source_name: str,
    units: Iterable[Mapping[str, str]],
    *,
    overrides: Mapping[str, str] | None = None,
) -> OutageAlignment:
    source = normalize_name(source_name)
    index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for unit in units:
        unit_name = unit["機組名稱"].strip()
        index[normalize_name(unit_name)].append((unit_name, unit["電廠名稱"].strip()))

    override = (overrides or {}).get(source)
    if override:
        matches = index.get(normalize_name(override), [])
        if len(matches) != 1:
            raise ValueError(f"歲修 override {source!r} -> {override!r} 無法唯一對應")
        return OutageAlignment(source, matches[0][0], matches[0][1], "override", (matches[0][0],))

    for candidate in outage_unit_candidates(source):
        matches = index.get(normalize_name(candidate), [])
        if len(matches) == 1:
            return OutageAlignment(
                source, matches[0][0], matches[0][1], "matched", (matches[0][0],)
            )
        if len(matches) > 1:
            names = tuple(item[0] for item in matches)
            return OutageAlignment(source, None, None, "ambiguous", names)

    if "#" not in source:
        prefix_matches = {
            item
            for normalized, matches in index.items()
            if normalized.startswith(source)
            for item in matches
        }
        if len(prefix_matches) == 1:
            unit_name, plant_name = next(iter(prefix_matches))
            return OutageAlignment(source, unit_name, plant_name, "matched", (unit_name,))
        if len(prefix_matches) > 1:
            names = tuple(sorted(item[0] for item in prefix_matches))
            return OutageAlignment(source, None, None, "ambiguous", names)

    return OutageAlignment(source, None, None, "unmatched", ())


def align_outage_rows(
    outage_rows: Iterable[Mapping[str, str]],
    units: Iterable[Mapping[str, str]],
    *,
    overrides: Mapping[str, str] | None = None,
) -> list[OutageAlignment]:
    units = list(units)
    return [align_outage_name(row["機組名稱"], units, overrides=overrides) for row in outage_rows]


def summarize_outage_alignment(results: Iterable[OutageAlignment]) -> dict[str, object]:
    results = list(results)
    counts = Counter(result.status for result in results)
    matched = counts["matched"] + counts["override"]
    return {
        "total": len(results),
        "matched": matched,
        "match_rate": matched / len(results) if results else 0.0,
        "status_counts": dict(sorted(counts.items())),
        "unresolved_names": sorted(
            {
                result.source_name
                for result in results
                if result.status not in {"matched", "override"}
            }
        ),
    }
