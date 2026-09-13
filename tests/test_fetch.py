from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ingest.fetch import Dataset, download_datasets


def test_download_archives_by_content_hash_and_updates_latest(tmp_path: Path) -> None:
    dataset = Dataset("fixture", "d000000", "fixture.csv", "fixture")
    payload = b"date,value\n20260101,1\n"

    manifest = download_datasets([dataset], data_root=tmp_path, downloader=lambda _url: payload)
    digest = hashlib.sha256(payload).hexdigest()

    assert (tmp_path / "raw/fixture.csv").read_bytes() == payload
    assert (tmp_path / f"archive/fixture/{digest}.csv").read_bytes() == payload
    saved_manifest = json.loads((tmp_path / "raw/manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest == manifest
    assert saved_manifest["resources"][0]["sha256"] == digest


def test_same_payload_reuses_archive_snapshot(tmp_path: Path) -> None:
    dataset = Dataset("fixture", "d000000", "fixture.csv", "fixture")
    payload = b"date,value\n20260101,1\n"

    download_datasets([dataset], data_root=tmp_path, downloader=lambda _url: payload)
    download_datasets([dataset], data_root=tmp_path, downloader=lambda _url: payload)

    assert len(list((tmp_path / "archive/fixture").glob("*.csv"))) == 1
