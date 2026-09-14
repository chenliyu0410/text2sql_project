"""Run reproducible alignment validation and write a machine-readable report."""

from __future__ import annotations

import csv
import json

import yaml

from align.crosswalk import parse_crosswalk, validate_crosswalk
from align.outage_align import align_outage_rows, summarize_outage_alignment
from align.pitfalls import generate_pitfalls
from ingest.validate import PROJECT_ROOT


def main() -> int:
    with (PROJECT_ROOT / "configs/align.yaml").open(encoding="utf-8") as handle:
        align_config = yaml.safe_load(handle)
    with (PROJECT_ROOT / "configs/outage_overrides.yaml").open(encoding="utf-8") as handle:
        overrides = yaml.safe_load(handle).get("overrides", {})
    with (PROJECT_ROOT / "taipower_align/crosswalk.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        crosswalk = parse_crosswalk(csv.DictReader(handle))
    with (PROJECT_ROOT / "taipower_align/units.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        units = list(csv.DictReader(handle))
    with (PROJECT_ROOT / "taipower_align/outage.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        outages = list(csv.DictReader(handle))

    ratio = align_config["ratio"]
    issues = validate_crosswalk(
        crosswalk,
        ratio_min=float(ratio["expected_min"]),
        ratio_max=float(ratio["expected_max"]),
    )
    outage_results = align_outage_rows(outages, units, overrides=overrides)
    outage_summary = summarize_outage_alignment(outage_results)
    pitfalls = generate_pitfalls(crosswalk, ratio_max=float(ratio["expected_max"]))
    report = {
        "status": "pass" if not issues and outage_summary["match_rate"] >= 0.9 else "fail",
        "crosswalk": {"count": len(crosswalk), "issues": issues},
        "outage": outage_summary,
        "pitfalls": {
            "count": len(pitfalls),
            "by_code": {
                code: sum(pitfall.code == code for pitfall in pitfalls)
                for code in sorted({pitfall.code for pitfall in pitfalls})
            },
        },
    }
    reports = PROJECT_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "alignment.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    unresolved = [
        f"{result.source_name}\t{result.status}\t{'|'.join(result.candidates)}"
        for result in outage_results
        if result.status not in {"matched", "override"}
    ]
    (reports / "outage_unmatched.txt").write_text(
        "source_name\tstatus\tcandidates\n" + "\n".join(dict.fromkeys(unresolved)) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report["status"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
