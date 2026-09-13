"""FastAPI application for the PowerQuery TW query pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints

from ingest.validate import PROJECT_ROOT
from serving.presentation import enrich_query_data
from serving.runtime import ServiceRuntime, build_runtime


class QueryRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def create_app(runtime: ServiceRuntime | None = None, *, static_dir: Path | None = None) -> FastAPI:
    assets = (static_dir or Path(__file__).with_name("static")).resolve()
    application = FastAPI(
        title="PowerQuery TW API",
        version="0.1.0",
        description="台電開放資料的可信任 Text2SQL 查詢介面",
    )
    application.state.runtime = runtime

    def current_runtime() -> ServiceRuntime:
        if application.state.runtime is None:
            try:
                application.state.runtime = build_runtime(root=PROJECT_ROOT)
            except (FileNotFoundError, OSError, ValueError) as error:
                raise HTTPException(
                    status_code=503,
                    detail="資料庫尚未就緒，請先執行 `make db`。",
                ) from error
        return application.state.runtime

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.plot.ly; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(assets / "index.html")

    @application.get("/api/health")
    def health() -> dict[str, object]:
        service = current_runtime()
        return {
            "success": True,
            "demo": not service.online_llm,
            "online_llm": service.online_llm,
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
        return {"is_training_complete": True, "training_status": "語料索引已就緒"}

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
        service = current_runtime()
        response = service.pipeline.query(payload.question).to_dict()
        if response["success"] and isinstance(response.get("data"), dict):
            response["data"] = enrich_query_data(response["data"])
        return response

    application.mount("/static", StaticFiles(directory=assets), name="static")
    return application


app = create_app()
