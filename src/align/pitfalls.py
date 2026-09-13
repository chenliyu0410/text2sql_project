"""Derive machine-readable semantic pitfalls from alignment results."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from align.crosswalk import CrosswalkRecord


@dataclass(frozen=True)
class Pitfall:
    code: str
    target_kind: str
    target_name: str
    severity: str
    reason: str
    suggestion: str
    evidence: dict[str, Any]


def generate_pitfalls(records: Iterable[CrosswalkRecord], *, ratio_max: float) -> list[Pitfall]:
    records = list(records)
    pitfalls: list[Pitfall] = []
    for record in records:
        if record.is_residual:
            pitfalls.append(
                Pitfall(
                    "RESIDUAL_TREND",
                    "column",
                    record.b_column,
                    "refuse",
                    "殘差欄的組成可能隨資料版本改變，不能作跨期趨勢比較。",
                    "改查同日系統指標，或使用粒度穩定的具名機組欄位。",
                    {"plants": list(record.plants)},
                )
            )

    named_plants = {
        plant for record in records if not record.is_residual for plant in record.plants
    }
    residual_plants = {plant for record in records if record.is_residual for plant in record.plants}
    for plant in sorted(named_plants & residual_plants):
        pitfalls.append(
            Pitfall(
                "PLANT_TOTAL_INCOMPLETE",
                "plant",
                plant,
                "disclose",
                "此電廠同時出現在具名欄位與全系統殘差欄，無法完整還原電廠總出力。",
                "改查具名機組或分廠的尖峰出力。",
                {"derived_from": "crosswalk"},
            )
        )

    for record in records:
        if record.ratio > ratio_max and not record.is_residual:
            pitfalls.append(
                Pitfall(
                    "KNOWN_CAPACITY_GAP",
                    "column",
                    record.b_column,
                    "disclose",
                    "實測最大出力高於主檔可對應裝置容量，主檔可能缺少機組。",
                    "可查詢出力，但應一併揭露主檔容量缺口。",
                    {
                        "ratio": record.ratio,
                        "capacity_wankw": record.capacity_wankw,
                        "observed_max_wankw": record.observed_max_wankw,
                    },
                )
            )
    return pitfalls
