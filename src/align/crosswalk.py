"""Pure crosswalk parsing and capacity-accounting checks."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CrosswalkRecord:
    b_column: str
    plants: tuple[str, ...]
    units: tuple[str, ...]
    n_plants: int
    n_units: int
    capacity_wankw: float
    observed_max_wankw: float
    ratio: float
    confidence: str
    is_residual: bool
    is_bucket: bool
    note: str


def clean_b_column(value: str) -> str:
    return value.strip().removesuffix("(萬瓩)").strip()


def capacity_ratio(capacity_kw: float, observed_wankw: float) -> float:
    capacity_wankw = capacity_kw / 10_000
    return observed_wankw / capacity_wankw if capacity_wankw else 0.0


def parse_crosswalk(rows: Iterable[Mapping[str, str]]) -> list[CrosswalkRecord]:
    records = []
    for row in rows:
        records.append(
            CrosswalkRecord(
                b_column=clean_b_column(row["b_column"]),
                plants=tuple(filter(None, (name.strip() for name in row["a_plant"].split("|")))),
                units=tuple(filter(None, (name.strip() for name in row["a_units"].split("|")))),
                n_plants=int(row["n_plants"]),
                n_units=int(row["n_units"]),
                capacity_wankw=float(row["cap_a_wankw"]),
                observed_max_wankw=float(row["obs_max_b"]),
                ratio=float(row["ratio"]),
                confidence=row["confidence"].strip(),
                is_residual=row["is_residual"] == "1",
                is_bucket=row["is_bucket"] == "1",
                note=row["note"].strip(),
            )
        )
    return records


def validate_crosswalk(
    records: Iterable[CrosswalkRecord], *, ratio_min: float, ratio_max: float
) -> list[str]:
    records = list(records)
    issues: list[str] = []
    columns = [record.b_column for record in records]
    if len(columns) != len(set(columns)):
        issues.append("b_column 不唯一")
    for record in records:
        if record.n_units != len(record.units):
            issues.append(f"{record.b_column}: n_units 與機組清單不符")
        if record.n_plants != len(set(record.plants)):
            issues.append(f"{record.b_column}: n_plants 與電廠清單不符")
        if record.capacity_wankw:
            calculated = record.observed_max_wankw / record.capacity_wankw
            if abs(calculated - record.ratio) > 0.005:
                issues.append(f"{record.b_column}: ratio 重算不一致")
        if not ratio_min <= record.ratio <= ratio_max and not record.note:
            issues.append(f"{record.b_column}: 比值異常但沒有審查備註")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path("taipower_align/crosswalk.csv"))
    parser.add_argument("--ratio-min", type=float, default=0.8)
    parser.add_argument("--ratio-max", type=float, default=1.06)
    args = parser.parse_args(argv)
    with args.path.open(encoding="utf-8-sig", newline="") as handle:
        records = parse_crosswalk(csv.DictReader(handle))
    issues = validate_crosswalk(records, ratio_min=args.ratio_min, ratio_max=args.ratio_max)
    print(json.dumps({"count": len(records), "issues": issues}, ensure_ascii=False, indent=2))
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
