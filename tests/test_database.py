from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ingest.build_db import build_database
from ingest.validate import PROJECT_ROOT, validate_configured_files


@pytest.mark.contract
def test_full_source_fixture_matches_documented_counts() -> None:
    report = validate_configured_files()

    assert report["status"] == "pass"
    assert report["counts"] == {
        "plants": 22,
        "units": 175,
        "dates": 577,
        "daily_system": 577,
        "generation_columns": 64,
        "mapped_columns": 43,
        "daily_peak": 36_928,
        "outages": 138,
    }
    assert report["date_range"] == {"min": "2025-01-01", "max": "2026-07-31"}


@pytest.mark.integration
def test_database_contains_star_schema_and_semantic_views(tmp_path: Path) -> None:
    target = tmp_path / "power.db"
    report = build_database(target)

    assert report["table_counts"]["dim_unit"] == 175
    assert report["table_counts"]["bridge_b_column"] == 43
    assert report["table_counts"]["dim_b_column"] == 64
    assert report["table_counts"]["fact_daily_peak"] == 36_928
    assert report["table_counts"]["fact_daily_system"] == 577
    assert report["table_counts"]["dim_outage"] == 138

    with sqlite3.connect(target) as connection:
        views = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view' ORDER BY name"
            )
        }
        assert views == {"v_outage", "v_peak", "v_system", "v_unit"}
        assert connection.execute("SELECT COUNT(*) FROM v_peak").fetchone()[0] == 36_928
        assert connection.execute("SELECT COUNT(*) FROM v_system").fetchone()[0] == 577
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM dim_outage WHERE date_status = 'invalid_range'"
            ).fetchone()[0]
            == 1
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        manifest = connection.execute(
            "SELECT data_start, data_end, data_checksum FROM meta_manifest WHERE id = 1"
        ).fetchone()
        assert manifest == (
            "2025-01-01",
            "2026-07-31",
            report["database_content_checksum"],
        )


@pytest.mark.integration
def test_rebuild_is_content_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "power.db"
    first = build_database(target, root=PROJECT_ROOT)
    second = build_database(target, root=PROJECT_ROOT)

    assert first["table_counts"] == second["table_counts"]
    assert first["database_content_checksum"] == second["database_content_checksum"]
