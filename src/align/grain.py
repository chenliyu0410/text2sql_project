"""Classify source columns by physical grain and fuel category."""

from __future__ import annotations

FUEL_CATEGORY = {
    "煤": "燃煤",
    "天然氣": "燃氣",
    "重油": "燃油",
    "輕柴油": "燃油",
    "水": "水力",
}
SOURCE_CATEGORY = {
    "核能": "核能",
    "民營電廠IPP": "IPP",
    "汽電共生": "汽電共生",
    "再生能源彙總": "再生",
}


def classify_grain(
    column: str,
    *,
    n_units: int = 0,
    n_plants: int = 0,
    is_residual: bool = False,
    is_bucket: bool = False,
) -> str:
    if is_residual:
        return "殘差桶"
    if is_bucket or n_plants > 1 or "(" in column:
        return "多機彙總"
    if n_units == 1 or ("#" in column and "發電" not in column):
        return "單機"
    if n_units > 1:
        return "分廠彙總"
    return "多機彙總"


def classify_category(fuels: set[str], *, source_category: str) -> str:
    categories = {FUEL_CATEGORY[fuel] for fuel in fuels if fuel in FUEL_CATEGORY}
    if categories:
        return "|".join(sorted(categories))
    return SOURCE_CATEGORY.get(source_category, source_category)
