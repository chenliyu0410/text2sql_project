"""FastAPI application for the PowerQuery TW query pipeline."""

from __future__ import annotations

import secrets
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal
from weakref import WeakSet

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints

from ingest.validate import PROJECT_ROOT
from serving.corpus_learning import CorpusLearningService
from serving.presentation import enrich_query_data
from serving.runtime import RuntimeManager, RuntimeMode, ServiceRuntime

SAFE_RUNTIME_ERRORS = {
    "線上模式尚未設定 API key。",
    "線上模式需要 API key；請在記憶體設定或使用 OPENAI_API_KEY。",
    "請先執行 `uv sync --extra online`。",
}
SWAGGER_UI_VERSION = "5.32.15"
SWAGGER_UI_JS_SRI = "sha384-m7zaGj7MPzU+G4lz2eyy73GxK9bbRDr9bB2CSdj8wodg2wu/Wnt6wsoLP3JD+RS9"
SWAGGER_UI_CSS_SRI = "sha384-fgyWYkUAamzuI8mJFu/xpRP0JWCJRwkwUwsYDoOYVHUJ8NQE5cENn8ib3ppwFFSX"
GENERIC_RUNTIME_ERROR = (
    "線上執行環境初始化失敗；請確認 online 套件、API key 與模型設定。原設定未變更。"
)
GENERIC_CONFIGURATION_ERROR = "執行環境設定無效；請檢查 configs、provider 與模型設定。"


def _safe_runtime_error(error: Exception) -> str:
    message = str(error)
    return message if message in SAFE_RUNTIME_ERRORS else GENERIC_RUNTIME_ERROR


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    execution_mode: Literal["offline", "online", "auto"] | None = None


class RuntimeSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["offline", "online", "auto"]
    api_key: SecretStr | None = None
    model: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    ] = None


class CorpusReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    reviewer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def create_app(runtime: ServiceRuntime | None = None, *, static_dir: Path | None = None) -> FastAPI:
    assets = (static_dir or Path(__file__).with_name("static")).resolve()
    application = FastAPI(
        title="PowerQuery TW API",
        version="0.2.0",
        description="台電開放資料的可信任 Text2SQL 查詢介面",
        docs_url=None,
        redoc_url=None,
    )
    application.state.runtime_manager = RuntimeManager(runtime) if runtime is not None else None
    application.state.learning_service = None
    application.state.learning_pipelines = WeakSet()
    application.state.initialization_lock = RLock()

    @application.exception_handler(RequestValidationError)
    async def sanitized_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request
        # FastAPI's default 422 payload echoes invalid input. Omitting that field
        # prevents malformed API-key or question bodies from being reflected.
        details = []
        for item in error.errors():
            sanitized = dict(item)
            sanitized.pop("input", None)
            details.append(sanitized)
        return JSONResponse(status_code=422, content=jsonable_encoder({"detail": details}))

    def current_manager() -> RuntimeManager:
        if application.state.runtime_manager is None:
            with application.state.initialization_lock:
                if application.state.runtime_manager is None:
                    try:
                        application.state.runtime_manager = RuntimeManager(root=PROJECT_ROOT)
                    except (FileNotFoundError, OSError) as error:
                        raise HTTPException(
                            status_code=503,
                            detail="資料庫尚未就緒，請先執行 `make db`。",
                        ) from error
                    except ValueError as error:
                        raise HTTPException(
                            status_code=503,
                            detail=GENERIC_CONFIGURATION_ERROR,
                        ) from error
                    except RuntimeError as error:
                        raise HTTPException(
                            status_code=503,
                            detail=_safe_runtime_error(error),
                        ) from error
        return application.state.runtime_manager

    def current_runtime(mode: RuntimeMode | None = None) -> ServiceRuntime:
        try:
            return current_manager().get_runtime(mode)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=_safe_runtime_error(error)) from error

    def current_learning(service: ServiceRuntime) -> CorpusLearningService:
        with application.state.initialization_lock:
            learning = application.state.learning_service
            if learning is None:
                learning = CorpusLearningService(
                    database=service.database,
                    canonical_corpus_path=service.root / "corpus/training_corpus.json",
                    benchmark_dir=service.root / "benchmarks",
                    pipeline=service.pipeline,
                )
                application.state.learning_service = learning
                application.state.learning_pipelines.add(service.pipeline)
            elif service.pipeline not in application.state.learning_pipelines:
                learning.attach_pipeline(service.pipeline)
                application.state.learning_pipelines.add(service.pipeline)
            return learning

    def required_learning(service: ServiceRuntime) -> CorpusLearningService:
        try:
            return current_learning(service)
        except (FileNotFoundError, OSError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail="語料學習工作區尚未就緒。") from error

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' https://cdn.plot.ly; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
                "frame-ancestors 'none'"
            )
        return response

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(assets / "index.html")

    @application.get("/docs", include_in_schema=False)
    def api_docs() -> HTMLResponse:
        nonce = secrets.token_urlsafe(24)
        swagger_js_url = (
            "https://cdn.jsdelivr.net/npm/"
            f"swagger-ui-dist@{SWAGGER_UI_VERSION}/swagger-ui-bundle.js"
        )
        swagger_css_url = (
            f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}/swagger-ui.css"
        )
        page = get_swagger_ui_html(
            openapi_url=application.openapi_url,
            title=f"{application.title} - Swagger UI",
            swagger_js_url=swagger_js_url,
            swagger_css_url=swagger_css_url,
            swagger_favicon_url="/static/favicon.svg",
        )
        body = page.body.decode("utf-8")
        body = body.replace(
            f'<link type="text/css" rel="stylesheet" href="{swagger_css_url}">',
            '<link type="text/css" rel="stylesheet" '
            f'href="{swagger_css_url}" integrity="{SWAGGER_UI_CSS_SRI}" '
            'crossorigin="anonymous">',
        )
        body = body.replace(
            f'<script src="{swagger_js_url}"></script>',
            f'<script src="{swagger_js_url}" integrity="{SWAGGER_UI_JS_SRI}" '
            'crossorigin="anonymous"></script>',
        )
        body = body.replace("<script", f'<script nonce="{nonce}"')
        docs_csp = (
            "default-src 'none'; "
            f"script-src 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            "style-src https://cdn.jsdelivr.net 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        return HTMLResponse(body, headers={"Content-Security-Policy": docs_csp})

    @application.get("/api/health")
    def health() -> dict[str, object]:
        try:
            service, mode = current_manager().runtime_and_status()
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=_safe_runtime_error(error)) from error
        return {
            "success": True,
            "demo": not service.online_llm,
            "online_llm": service.online_llm,
            "mode": mode,
            "data_range": {"start": service.data_range[0], "end": service.data_range[1]},
        }

    @application.get("/api/stats")
    def stats() -> dict[str, object]:
        service = current_runtime()

        def scalar(sql: str) -> int:
            _columns, rows = service.executor.execute(sql, ())
            return int(rows[0][0])

        return {
            "success": True,
            "data": {
                "total_records": scalar("SELECT COUNT(*) FROM v_peak LIMIT 1"),
                "total_units": scalar("SELECT COUNT(*) FROM v_unit LIMIT 1"),
                "outage_records": scalar("SELECT COUNT(*) FROM v_outage LIMIT 1"),
                "date_range": f"{service.data_range[0]} ~ {service.data_range[1]}",
            },
        }

    @application.get("/api/training-status")
    def training_status() -> dict[str, object]:
        status = required_learning(current_runtime()).status()
        ready = bool(status["workspace_ready"] and status["index_synchronized"])
        return {
            "success": True,
            "is_training_complete": ready,
            "training_status": "語料學習工作區已就緒" if ready else "語料索引待同步",
            "data": status,
        }

    @application.get("/api/runtime/llm")
    def runtime_status() -> dict[str, object]:
        return {"success": True, "data": current_manager().status()}

    @application.put("/api/runtime/llm")
    def configure_runtime(payload: RuntimeSettingsRequest) -> dict[str, object]:
        updates: dict[str, object] = {"mode": payload.mode}
        if "model" in payload.model_fields_set and payload.model is not None:
            updates["model"] = payload.model
        if "api_key" in payload.model_fields_set:
            updates["api_key"] = (
                payload.api_key.get_secret_value() if payload.api_key is not None else None
            )
        try:
            status = current_manager().configure_and_status(**updates)
        except (RuntimeError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=_safe_runtime_error(error)) from error
        return {"success": True, "data": status}

    @application.get("/api/corpus/entries")
    def corpus_entries(
        state: Literal[
            "all", "validating", "pending_review", "promoted", "rejected", "ignored"
        ] = "all",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, object]:
        learning = required_learning(current_runtime())
        entries = learning.list_entries(state=None if state == "all" else state, limit=limit)
        return {
            "success": True,
            "data": {
                "state": state,
                "entries": entries,
                "returned": len(entries),
            },
        }

    @application.get("/api/corpus/events")
    def corpus_events(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, object]:
        events = required_learning(current_runtime()).list_events(limit=limit)
        return {"success": True, "data": {"events": events, "returned": len(events)}}

    @application.post("/api/corpus/entries/{candidate_id}/review")
    def review_corpus_entry(
        candidate_id: str,
        payload: CorpusReviewRequest,
    ) -> dict[str, object]:
        service = current_runtime()
        learning = required_learning(service)
        try:
            entry = learning.review(
                candidate_id,
                approve=payload.decision == "approve",
                reviewer=payload.reviewer,
                pipeline=service.pipeline,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="找不到指定的語料候選。") from error
        except ValueError as error:
            raise HTTPException(
                status_code=409,
                detail="候選狀態已變更，或目前不可審核。",
            ) from error
        return {"success": True, "data": entry}

    @application.get("/api/examples")
    def examples() -> dict[str, object]:
        return {
            "success": True,
            "data": [
                "2026年7月備轉容量率最低是哪一天？",
                "2026年7月20日出力前五名機組",
                "列出台中發電廠所有設備",
                "天然氣機組共有幾台？",
                "2026年三月有哪些機組在歲修？",
            ],
        }

    @application.post("/api/query")
    def query(payload: QueryRequest) -> dict[str, object]:
        service = current_runtime(payload.execution_mode)
        learning: CorpusLearningService | None
        try:
            learning = current_learning(service)
        except (FileNotFoundError, OSError, ValueError, RuntimeError):
            learning = None
        pipeline_response = service.pipeline.query(payload.question)
        response = pipeline_response.to_dict()
        if response["success"] and isinstance(response.get("data"), dict):
            learning_result = (
                learning.observe(pipeline_response, pipeline=service.pipeline)
                if learning is not None
                else {
                    "accepted": False,
                    "status": "error",
                    "reason": "learning_workspace_unavailable",
                }
            )
            response["data"] = enrich_query_data(response["data"])
            response["data"]["runtime"] = {
                "mode": service.mode,
                "provider": service.provider,
                "model": service.model,
            }
            response["data"]["learning"] = learning_result
        return response

    application.mount("/static", StaticFiles(directory=assets), name="static")
    return application


app = create_app()
