from __future__ import annotations

import csv

from align.outage_align import align_outage_name, align_outage_rows, summarize_outage_alignment
from ingest.validate import PROJECT_ROOT


def _rows(name: str) -> list[dict[str, str]]:
    with (PROJECT_ROOT / f"taipower_align/{name}").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_outage_name_alignment_handles_direct_converted_and_ambiguous_names() -> None:
    units = _rows("units.csv")

    assert align_outage_name("明潭#5", units).unit_name == "明潭#5機"
    assert align_outage_name("台中#10", units).unit_name == "中十機"
    assert align_outage_name("大潭#7", units).unit_name == "#GT7"
    assert align_outage_name("興達CC#3", units).unit_name == "興達複三機"
    assert align_outage_name("立霧", units).status == "ambiguous"
    assert align_outage_name("大潭#9", units).status == "unmatched"


def test_official_outage_snapshot_meets_alignment_threshold() -> None:
    results = align_outage_rows(_rows("outage.csv"), _rows("units.csv"))
    summary = summarize_outage_alignment(results)

    assert summary["total"] == 138
    assert summary["matched"] == 125
    assert summary["match_rate"] >= 0.90
    assert summary["status_counts"] == {"ambiguous": 1, "matched": 125, "unmatched": 12}
    assert summary["unresolved_names"] == ["大潭#8", "大潭#9", "立霧", "興達新#1"]
