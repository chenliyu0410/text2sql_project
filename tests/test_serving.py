import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ingest.build_db import build_database
from ingest.validate import PROJECT_ROOT
from serving import runtime as runtime_module
from serving.app import create_app
from serving.runtime import build_runtime


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory):
    database = tmp_path_factory.mktemp("serving") / "power.db"
    build_database(database)
    runtime = build_runtime(database=database)
    with TestClient(create_app(runtime)) as test_client:
        yield test_client


def _all_mapping_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _all_mapping_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _all_mapping_keys(child)}
    return set()


def _reset_offline_runtime(client: TestClient) -> dict[str, object]:
    response = client.put(
        "/api/runtime/llm",
        json={"mode": "offline", "api_key": None},
    )
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.e2e
def test_health_stats_and_static_frontend(client: TestClient) -> None:
    home = client.get("/")
    assert home.status_code == 200
    assert "PowerQuery TW" in home.text
    assert "default-src 'self'" in home.headers["content-security-policy"]
    for view in ("query", "overview", "corpus", "settings", "docs"):
        assert f'data-view="{view}"' in home.text
        assert f'data-panel="{view}"' in home.text
    assert 'id="runtimeForm"' in home.text
    assert 'id="clearRuntimeKey"' in home.text
    assert '<option value="">沿用預設模式</option>' in home.text
    assert 'option value="auto">自動判斷</option>' in home.text
    assert 'id="corpusEntries"' in home.text
    assert 'href="/docs"' in home.text

    stylesheet = client.get("/static/app.css")
    assert stylesheet.status_code == 200
    assert ".chart > svg" in stylesheet.text
    assert ".chart svg {" not in stylesheet.text
    assert ".plotly-chart .main-svg { position: absolute" in stylesheet.text
    assert ".mode-option:has(input:focus-visible)" in stylesheet.text

    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "if (selectedMode) requestBody.execution_mode = selectedMode" in script.text
    assert "SENSITIVE_HISTORY_PATTERNS" in script.text
    assert 'sidebar.setAttribute("aria-hidden", "true")' in script.text

    health = client.get("/api/health").json()
    assert health["success"] is True
    assert health["data_range"] == {"start": "2025-01-01", "end": "2026-07-31"}
    stats = client.get("/api/stats").json()["data"]
    assert stats["total_records"] == 36_928
    assert stats["total_units"] == 175
    assert stats["outage_records"] == 138

    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger-ui-dist@5.32.15" in docs.text
    assert "sha384-m7zaGj7MPzU+G4lz2eyy73GxK9bbRDr9bB2CSdj8wodg2wu/Wnt6wsoLP3JD+RS9" in docs.text
    assert "sha384-fgyWYkUAamzuI8mJFu/xpRP0JWCJRwkwUwsYDoOYVHUJ8NQE5cENn8ib3ppwFFSX" in docs.text
    assert 'href="/static/favicon.svg"' in docs.text
    nonce = re.search(r'<script nonce="([^"]+)"', docs.text)
    assert nonce is not None
    assert (
        f"script-src 'nonce-{nonce.group(1)}' https://cdn.jsdelivr.net"
        in docs.headers["content-security-policy"]
    )
    assert "cdn.jsdelivr.net" not in home.headers["content-security-policy"]


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
def test_runtime_status_never_exposes_credentials(client: TestClient) -> None:
    response = client.get("/api/runtime/llm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert _all_mapping_keys(payload).isdisjoint({"api_key", "key", "credential"})
    assert "OPENAI_API_KEY" not in response.text


@pytest.mark.e2e
def test_validation_errors_do_not_reflect_sensitive_input(client: TestClient) -> None:
    secret = "sk-malformed-body-must-not-be-reflected"

    response = client.put(
        "/api/runtime/llm",
        json={"mode": "offline", "api_key": [secret]},
    )

    assert response.status_code == 422
    assert secret not in response.text
    assert all("input" not in item for item in response.json()["detail"])


@pytest.mark.e2e
def test_explicit_null_model_preserves_current_runtime_model(client: TestClient) -> None:
    before = _reset_offline_runtime(client)

    response = client.put(
        "/api/runtime/llm",
        json={"mode": "offline", "model": None},
    )

    assert response.status_code == 200
    assert response.json()["data"]["model"] == before["model"]


@pytest.mark.e2e
def test_offline_runtime_keeps_and_clears_key_only_in_memory(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    baseline = _reset_offline_runtime(client)
    manager = client.app.state.runtime_manager
    secret = "sk-test-memory-only-never-return"

    try:
        response = client.put(
            "/api/runtime/llm",
            json={"mode": "offline", "api_key": secret},
        )
        fetched = client.get("/api/runtime/llm")

        assert response.status_code == 200
        assert response.json()["data"]["active_mode"] == "offline"
        assert response.json()["data"]["online_configured"] is True
        assert manager._api_key == secret
        assert secret not in response.text
        assert secret not in fetched.text
        assert secret not in repr(manager)
        assert _all_mapping_keys(fetched.json()).isdisjoint({"api_key", "key", "credential"})
    finally:
        restored = _reset_offline_runtime(client)

    assert restored == baseline
    assert manager._api_key is None


@pytest.mark.e2e
def test_failed_online_adapter_configuration_rolls_back_atomically(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    baseline = _reset_offline_runtime(client)
    manager = client.app.state.runtime_manager
    secret = "sk-test-failed-adapter-never-return"

    class BrokenOpenAILLM:
        def __init__(self, **kwargs: object):
            raise RuntimeError(f"adapter rejected credential {kwargs['api_key']}")

    monkeypatch.setattr(runtime_module, "OpenAILLM", BrokenOpenAILLM)
    response = client.put(
        "/api/runtime/llm",
        json={"mode": "online", "model": "broken-model", "api_key": secret},
    )

    assert response.status_code == 400
    assert response.json()["detail"].startswith("線上執行環境初始化失敗")
    assert secret not in response.text
    assert client.get("/api/runtime/llm").json()["data"] == baseline
    assert secret not in repr(manager)
    assert "broken-model" not in repr(manager)


@pytest.mark.e2e
def test_query_can_force_offline_mode_without_changing_default(client: TestClient) -> None:
    default_mode = client.get("/api/runtime/llm").json()["data"]["default_mode"]

    response = client.post(
        "/api/query",
        json={
            "question": "2026年7月20日出力前五名機組",
            "execution_mode": "offline",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["runtime"]["mode"] == "offline"
    assert client.get("/api/runtime/llm").json()["data"]["default_mode"] == default_mode


@pytest.mark.e2e
def test_successful_query_learning_is_inspectable_without_persisted_rows(
    client: TestClient,
) -> None:
    before = client.get("/api/training-status").json()["data"]
    question = "請列出2026年6月每日備轉容量率，供服務整合測試調閱"

    response = client.post(
        "/api/query",
        json={"question": question, "execution_mode": "offline"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    learning = payload["data"]["learning"]
    candidate_id = learning["id"]
    assert learning["question"] == question
    assert learning["status"] in {"promoted", "rejected", "ignored"}

    status_response = client.get("/api/training-status")
    entries_response = client.get("/api/corpus/entries", params={"state": "all", "limit": 500})
    events_response = client.get("/api/corpus/events", params={"limit": 500})

    assert status_response.status_code == 200
    assert entries_response.status_code == 200
    assert events_response.status_code == 200
    status = status_response.json()["data"]
    entries = entries_response.json()["data"]["entries"]
    events = events_response.json()["data"]["events"]
    entry = next(item for item in entries if item["id"] == candidate_id)
    candidate_events = [item for item in events if item.get("candidate_id") == candidate_id]

    assert status["candidate_counts"]["total"] == before["candidate_counts"]["total"] + 1
    assert status["latest_event"]["candidate_id"] == candidate_id
    assert entry["result_checksum"]
    assert candidate_events
    assert "rows" not in _all_mapping_keys(entry)
    assert "rows" not in _all_mapping_keys(candidate_events)


@pytest.mark.e2e
def test_refusal_does_not_create_a_learning_candidate(client: TestClient) -> None:
    before_status = client.get("/api/training-status").json()["data"]
    before_events = client.get("/api/corpus/events", params={"limit": 500}).json()["data"]

    response = client.post(
        "/api/query",
        json={
            "question": "台中一號機去年尖峰出力總和",
            "execution_mode": "offline",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    after_status = client.get("/api/training-status").json()["data"]
    after_events = client.get("/api/corpus/events", params={"limit": 500}).json()["data"]
    assert after_status["candidate_counts"]["total"] == before_status["candidate_counts"]["total"]
    assert after_events["events"] == before_events["events"]


@pytest.mark.e2e
def test_pending_online_candidate_can_be_reviewed_locally(client: TestClient) -> None:
    _reset_offline_runtime(client)
    client.get("/api/training-status")
    runtime = client.app.state.runtime_manager.get_runtime("offline")
    learning = client.app.state.learning_service
    sql = 'SELECT "日期" FROM v_system WHERE "日期" = ? LIMIT 1'
    params = ("2026-07-09",)
    columns, rows = runtime.executor.execute(sql, params)
    pending = learning.submit(
        question="2026年7月9日系統日期線上候選審核測試",
        sql=sql,
        params=params,
        intent="system_metric",
        source="llm",
        columns=columns,
        rows=rows,
        pipeline=runtime.pipeline,
    )
    assert pending["status"] == "pending_review"

    response = client.post(
        f"/api/corpus/entries/{pending['id']}/review",
        json={"decision": "reject", "reviewer": "local-test-operator"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "rejected"
    repeated = client.post(
        f"/api/corpus/entries/{pending['id']}/review",
        json={"decision": "approve", "reviewer": "local-test-operator"},
    )
    assert repeated.status_code == 409


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
