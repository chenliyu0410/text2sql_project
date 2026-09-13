from __future__ import annotations

import csv
from collections import Counter

from align.crosswalk import parse_crosswalk
from align.pitfalls import generate_pitfalls
from ingest.validate import PROJECT_ROOT


def test_pitfalls_are_derived_from_crosswalk() -> None:
    with (PROJECT_ROOT / "taipower_align/crosswalk.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        records = parse_crosswalk(csv.DictReader(handle))

    pitfalls = generate_pitfalls(records, ratio_max=1.06)
    counts = Counter(pitfall.code for pitfall in pitfalls)

    assert counts == {
        "RESIDUAL_TREND": 2,
        "PLANT_TOTAL_INCOMPLETE": 6,
        "KNOWN_CAPACITY_GAP": 2,
    }
    assert {pitfall.target_name for pitfall in pitfalls if pitfall.code == "RESIDUAL_TREND"} == {
        "氣渦輪",
        "其他小水力",
    }
