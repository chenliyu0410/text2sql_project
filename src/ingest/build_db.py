"""Build the deterministic SQLite semantic layer from validated CSV artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ingest.validate import (
    DAILY_SYSTEM_COLUMNS,
    PROJECT_ROOT,
    parse_number,
    parse_source_date,
    parse_unit_date,
    read_csv,
    resolve_configured_paths,
    validate_files,
)

SCHEMA_VERSION = "1"


def _clean_b_column(value: str) -> str:
    return value.strip().removesuffix("(萬瓩)").strip()


def _text(row: dict[str, str], key: str) -> str:
    return row.get(key, "").strip()


def _load_align_limits(root: Path) -> tuple[float, float]:
    with (root / "configs/align.yaml").open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    return float(config["ratio"]["expected_min"]), float(config["ratio"]["expected_max"])


def _load_rows(paths: dict[str, Path]) -> dict[str, list[dict[str, str]]]:
    return {
        name: read_csv(paths[name])[1]
        for name in ("units_csv", "daily_csv", "crosswalk_csv", "daily_long_csv")
    }


def _insert_plants_and_units(
    connection: sqlite3.Connection, units: list[dict[str, str]]
) -> dict[str, list[int]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in units:
        grouped[_text(row, "電廠名稱")].append(row)

    unit_ids_by_name: dict[str, list[int]] = defaultdict(list)
    for plant_id, plant_name in enumerate(sorted(grouped), start=1):
        rows = grouped[plant_name]
        first = rows[0]
        fuels = sorted({_text(row, "燃料種類") for row in rows})
        address = "".join(
            _text(first, column) for column in ("地址-縣市鄉鎮", "地址-村里", "地址-街路門牌")
        )
        connection.execute(
            """INSERT INTO dim_plant
               (id, plant_name, postal_code, county, address, phone, fax, primary_fuel)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                plant_id,
                plant_name,
                _text(first, "郵遞區號"),
                _text(first, "地址-縣市鄉鎮"),
                address,
                _text(first, "連絡電話"),
                _text(first, "傳真電話"),
                "|".join(fuels),
            ),
        )
        for row in sorted(rows, key=lambda item: _text(item, "機組名稱")):
            unit_id = connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM dim_unit"
            ).fetchone()[0]
            commercial_date = _text(row, "商轉日期")
            parsed_date, date_precision = (
                parse_unit_date(commercial_date, context="units.csv")
                if commercial_date
                else (None, None)
            )
            connection.execute(
                """INSERT INTO dim_unit
                   (id, plant_id, unit_name, commercial_date, commercial_date_raw,
                    commercial_date_precision, capacity_kw, fuel)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    unit_id,
                    plant_id,
                    _text(row, "機組名稱"),
                    parsed_date,
                    commercial_date or None,
                    date_precision,
                    int(_text(row, "裝置容量(瓩)")),
                    _text(row, "燃料種類"),
                ),
            )
            unit_ids_by_name[_text(row, "機組名稱")].append(unit_id)
    return unit_ids_by_name


def _insert_dates_and_system(connection: sqlite3.Connection, daily: list[dict[str, str]]) -> None:
    for row in daily:
        date = parse_source_date(row["日期"], context="daily.csv")
        year, month, day = (int(part) for part in date.split("-"))
        connection.execute("INSERT INTO dim_date VALUES (?, ?, ?, ?)", (date, year, month, day))
        values = [
            parse_number(row[column], context=column, allow_empty=True)
            for column in DAILY_SYSTEM_COLUMNS
        ]
        connection.execute(
            """INSERT INTO fact_daily_system
               (date, net_peak_supply_wankw, peak_load_wankw, operating_reserve_wankw,
                operating_reserve_rate_pct, industrial_usage_million_kwh,
                residential_usage_million_kwh)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (date, *values),
        )


def _insert_columns_and_crosswalk(
    connection: sqlite3.Connection,
    daily_long: list[dict[str, str]],
    crosswalk: list[dict[str, str]],
    unit_ids_by_name: dict[str, list[int]],
) -> dict[str, int]:
    crosswalk_by_column = {_clean_b_column(row["b_column"]): row for row in crosswalk}
    column_metadata: dict[str, tuple[str, str]] = {}
    for row in daily_long:
        column = _text(row, "b_column")
        metadata = (_text(row, "grain"), _text(row, "category"))
        previous = column_metadata.setdefault(column, metadata)
        if previous != metadata:
            raise ValueError(f"{column} 的粒度或類別在 daily_long.csv 中不一致")

    ids: dict[str, int] = {}
    for column_id, column in enumerate(sorted(column_metadata), start=1):
        grain, category = column_metadata[column]
        has_master = int(column in crosswalk_by_column)
        connection.execute(
            "INSERT INTO dim_b_column VALUES (?, ?, ?, ?, ?)",
            (column_id, column, grain, category, has_master),
        )
        ids[column] = column_id

    for bridge_id, column in enumerate(sorted(crosswalk_by_column), start=1):
        row = crosswalk_by_column[column]
        column_id = ids[column]
        connection.execute(
            """INSERT INTO bridge_b_column
               (id, b_column_id, a_plant, n_plants, n_units, cap_a_wankw, obs_max_b,
                ratio, confidence, is_residual, is_bucket, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bridge_id,
                column_id,
                _text(row, "a_plant"),
                int(row["n_plants"]),
                int(row["n_units"]),
                float(row["cap_a_wankw"]),
                float(row["obs_max_b"]),
                float(row["ratio"]),
                _text(row, "confidence"),
                int(row["is_residual"]),
                int(row["is_bucket"]),
                _text(row, "note"),
            ),
        )
        for unit_name in filter(
            None, (_text_value.strip() for _text_value in row["a_units"].split("|"))
        ):
            candidates = unit_ids_by_name.get(unit_name, [])
            if len(candidates) != 1:
                raise ValueError(f"對齊機組 {unit_name!r} 無法唯一對應 dim_unit")
            connection.execute(
                "INSERT INTO bridge_b_column_unit VALUES (?, ?)", (column_id, candidates[0])
            )
    return ids


def _insert_daily_peak(
    connection: sqlite3.Connection,
    daily_long: list[dict[str, str]],
    column_ids: dict[str, int],
) -> None:
    rows = (
        (
            parse_source_date(row["日期"], context="daily_long.csv"),
            column_ids[_text(row, "b_column")],
            parse_number(row["尖峰出力_萬瓩"], context="daily_long.csv"),
        )
        for row in daily_long
    )
    connection.executemany("INSERT INTO fact_daily_peak VALUES (?, ?, ?)", rows)


def _insert_derived_pitfalls(connection: sqlite3.Connection, *, ratio_max: float) -> None:
    residual_rows = connection.execute(
        """SELECT c.b_column, b.a_plant
           FROM bridge_b_column AS b
           JOIN dim_b_column AS c ON c.id = b.b_column_id
           WHERE b.is_residual = 1"""
    ).fetchall()
    for column, plants in residual_rows:
        connection.execute(
            """INSERT INTO meta_pitfall
               (pitfall_code, target_kind, target_name, severity, reason, suggestion, evidence)
               VALUES (?, 'column', ?, 'refuse', ?, ?, ?)""",
            (
                "RESIDUAL_TREND",
                column,
                "殘差欄的組成可能隨資料版本改變，不能作跨期趨勢比較。",
                "改查同日系統指標，或使用粒度穩定的具名機組欄位。",
                json.dumps({"plants": plants.split("|")}, ensure_ascii=False),
            ),
        )

    named_plants: set[str] = set()
    residual_plants: set[str] = set()
    for plants, is_residual in connection.execute(
        "SELECT a_plant, is_residual FROM bridge_b_column"
    ):
        target = residual_plants if is_residual else named_plants
        target.update(filter(None, plants.split("|")))
    for plant in sorted(named_plants & residual_plants):
        connection.execute(
            """INSERT INTO meta_pitfall
               (pitfall_code, target_kind, target_name, severity, reason, suggestion, evidence)
               VALUES ('PLANT_TOTAL_INCOMPLETE', 'plant', ?, 'disclose', ?, ?, ?)""",
            (
                plant,
                "此電廠同時出現在具名欄位與全系統殘差欄，無法完整還原電廠總出力。",
                "改查具名機組或分廠的尖峰出力。",
                json.dumps({"derived_from": "crosswalk"}, ensure_ascii=False),
            ),
        )

    for column, ratio, capacity, observed in connection.execute(
        """SELECT c.b_column, b.ratio, b.cap_a_wankw, b.obs_max_b
           FROM bridge_b_column AS b
           JOIN dim_b_column AS c ON c.id = b.b_column_id
           WHERE b.ratio > ? AND b.is_residual = 0""",
        (ratio_max,),
    ):
        connection.execute(
            """INSERT INTO meta_pitfall
               (pitfall_code, target_kind, target_name, severity, reason, suggestion, evidence)
               VALUES ('KNOWN_CAPACITY_GAP', 'column', ?, 'disclose', ?, ?, ?)""",
            (
                column,
                "實測最大出力高於主檔可對應裝置容量，主檔可能缺少機組。",
                "可查詢出力，但應一併揭露主檔容量缺口。",
                json.dumps(
                    {
                        "ratio": ratio,
                        "capacity_wankw": capacity,
                        "observed_max_wankw": observed,
                    },
                    ensure_ascii=False,
                ),
            ),
        )


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "dim_plant",
        "dim_unit",
        "dim_date",
        "dim_b_column",
        "bridge_b_column",
        "bridge_b_column_unit",
        "fact_daily_peak",
        "fact_daily_system",
        "dim_outage",
        "meta_pitfall",
    )
    return {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }


def _database_content_checksum(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for table in (
        "dim_plant",
        "dim_unit",
        "dim_date",
        "dim_b_column",
        "bridge_b_column",
        "bridge_b_column_unit",
        "fact_daily_peak",
        "fact_daily_system",
        "dim_outage",
        "meta_pitfall",
    ):
        digest.update(table.encode())
        for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY 1, 2'):
            digest.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode())
    return digest.hexdigest()


def build_database(
    target: Path,
    *,
    root: Path = PROJECT_ROOT,
    report_path: Path | None = None,
) -> dict[str, Any]:
    paths = resolve_configured_paths(root)
    validation = validate_files(
        paths["units_csv"],
        paths["daily_csv"],
        paths["crosswalk_csv"],
        paths["daily_long_csv"],
    )
    rows = _load_rows(paths)
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    lower_ratio, upper_ratio = _load_align_limits(root)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-", suffix=".db", dir=target.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with closing(sqlite3.connect(temporary_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript((root / "src/ingest/schema.sql").read_text(encoding="utf-8"))
            unit_ids = _insert_plants_and_units(connection, rows["units_csv"])
            _insert_dates_and_system(connection, rows["daily_csv"])
            column_ids = _insert_columns_and_crosswalk(
                connection, rows["daily_long_csv"], rows["crosswalk_csv"], unit_ids
            )
            _insert_daily_peak(connection, rows["daily_long_csv"], column_ids)
            _insert_derived_pitfalls(connection, ratio_max=upper_ratio)

            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise ValueError(f"外鍵驗證失敗：{foreign_key_errors[:3]}")
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"SQLite quick_check 失敗：{integrity}")

            counts = _table_counts(connection)
            content_checksum = _database_content_checksum(connection)
            source_hashes = json.dumps(validation["source_sha256"], sort_keys=True)
            connection.execute(
                """INSERT INTO meta_manifest
                   (id, schema_version, data_version, data_start, data_end, built_at,
                    source_sha256, table_counts, data_checksum)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    SCHEMA_VERSION,
                    validation["data_checksum"][:16],
                    validation["date_range"]["min"],
                    validation["date_range"]["max"],
                    datetime.now(UTC).isoformat(),
                    source_hashes,
                    json.dumps(counts, sort_keys=True),
                    content_checksum,
                ),
            )
            connection.commit()
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)

    report = {
        **validation,
        "schema_version": SCHEMA_VERSION,
        "database": str(target),
        "table_counts": counts,
        "database_content_checksum": content_checksum,
        "ratio_thresholds": {"expected_min": lower_ratio, "expected_max": upper_ratio},
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    paths = resolve_configured_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=paths["database"])
    parser.add_argument("--report", type=Path, default=paths["data_quality_report"])
    args = parser.parse_args(argv)
    report = build_database(args.output, report_path=args.report)
    counts = report["table_counts"]
    print(
        f"已建立 {args.output}：{counts['dim_unit']} 機組、"
        f"{counts['bridge_b_column']} 對應欄位、{counts['fact_daily_peak']} 尖峰出力列。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
