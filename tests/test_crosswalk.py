from __future__ import annotations

import csv

import yaml

from align.crosswalk import capacity_ratio, parse_crosswalk, validate_crosswalk
from ingest.validate import PROJECT_ROOT


def test_capacity_ratio_converts_kw_to_wankw() -> None:
    assert capacity_ratio(800_000, 80.3) == 1.00375


def test_fixed_crosswalk_has_43_reviewed_unique_rows() -> None:
    with (PROJECT_ROOT / "taipower_align/crosswalk.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        records = parse_crosswalk(csv.DictReader(handle))
    with (PROJECT_ROOT / "configs/align.yaml").open(encoding="utf-8") as handle:
        ratio = yaml.safe_load(handle)["ratio"]

    assert len(records) == 43
    assert len({record.b_column for record in records}) == 43
    assert sum(record.n_units for record in records) == 175
    assert (
        validate_crosswalk(
            records,
            ratio_min=float(ratio["expected_min"]),
            ratio_max=float(ratio["expected_max"]),
        )
        == []
    )
