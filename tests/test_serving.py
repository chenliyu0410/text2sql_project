from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingest.build_db import build_database
from ingest.validate import PROJECT_ROOT
from serving.app import create_app
from serving.runtime import build_runtime


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory):
    database = tmp_path_factory.mktemp("serving") / "power.db"
    build_database(database)
    runtime = build_runtime(database=database)
    with TestClient(create_app(runtime)) as test_client:
        yield test_client


@pytest.mark.e2e
def test_health_stats_and_static_frontend(client: TestClient) -> None:
    home = client.get("/")
    assert home.status_code == 200
    assert "PowerQuery TW" in home.text
    assert "default-src 'self'" in home.headers["content-security-policy"]

    health = client.get("/api/health").json()
    assert health["success"] is True
    assert health["data_range"] == {"start": "2025-01-01", "end": "2026-07-31"}
    stats = client.get("/api/stats").json()["data"]
    assert stats["total_records"] == 36_928
    assert stats["total_units"] == 175
    assert stats["outage_records"] == 138


@pytest.mark.e2e
def test_query_endpoint_returns_traceable_chart_and_rows(client: TestClient) -> None:
    response = client.post("/api/query", json={"question": "2026年6月每日備轉容量率"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["record_count"] == 30
    assert data["chart_spec"]["kind"] == "line"
    assert data["chart_spec"]["data"][0]["x"] == [row[0] for row in data["rows"]]
    assert any(item["stage"] == "sql_guard" for item in data["trace"])


@pytest.mark.e2e
def test_semantic_refusal_is_a_structured_business_response(client: TestClient) -> None:
    response = client.post("/api/query", json={"question": "台中一號機去年尖峰出力總和"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "PEAK_SUM_ACROSS_DAYS"
    assert payload["severity"] == "refuse"


def test_query_validation_rejects_blank_input(client: TestClient) -> None:
    assert client.post("/api/query", json={"question": "   "}).status_code == 422


def test_missing_database_is_reported_as_unavailable(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_runtime(database=tmp_path / "missing.db", root=PROJECT_ROOT)
