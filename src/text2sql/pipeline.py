"""Guarded Text2SQL orchestration with deterministic routing and bounded retries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Protocol

from text2sql.corpus import load_corpus
from text2sql.entities import Entities, extract_entities
from text2sql.llm import GeneratedQuery, LLMProtocol, parse_generated_query
from text2sql.prompt import build_prompt
from text2sql.retriever import TfidfRetriever
from text2sql.router import route
from text2sql.sql_guard import SqlGuard, SqlGuardResult

RunSql = Callable[[str, tuple[object, ...]], tuple[list[str], list[tuple[object, ...]]]]


@dataclass(frozen=True)
class SemanticDecision:
    severity: str = "pass"
    code: str = "OK"
    reason: str = ""
    suggestions: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)


class SemanticGuardProtocol(Protocol):
    def check_question(self, question: str, entities: Entities) -> SemanticDecision: ...

    def check_sql(
        self, question: str, query: GeneratedQuery, entities: Entities
    ) -> SemanticDecision: ...


class AllowAllSemanticGuard:
    def check_question(self, question: str, entities: Entities) -> SemanticDecision:
        return SemanticDecision()

    def check_sql(
        self, question: str, query: GeneratedQuery, entities: Entities
    ) -> SemanticDecision:
        return SemanticDecision()


@dataclass(frozen=True)
class PipelineResponse:
    success: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error: str | None = None
    severity: str | None = None
    suggestions: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Text2SQLPipeline:
    def __init__(
        self,
        *,
        llm: LLMProtocol,
        sql_guard: SqlGuard,
        run_sql: RunSql,
        corpus_path: Any,
        data_range: tuple[str, str],
        peak_columns: set[str],
        semantic_guard: SemanticGuardProtocol | None = None,
        max_attempts: int = 3,
        top_k: int = 5,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts 必須至少是 1")
        self.llm = llm
        self.sql_guard = sql_guard
        self.run_sql = run_sql
        self.corpus = load_corpus(corpus_path)
        self.retriever = TfidfRetriever(self.corpus["examples"])
        self.data_range = data_range
        self.peak_columns = peak_columns
        self.semantic_guard = semantic_guard or AllowAllSemanticGuard()
        self.max_attempts = max_attempts
        self.top_k = top_k

    @staticmethod
    def _trace(trace: list[dict[str, Any]], stage: str, started: float, **details: Any) -> None:
        trace.append(
            {
                "stage": stage,
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                **details,
            }
        )

    @staticmethod
    def _semantic_error(
        decision: SemanticDecision, trace: list[dict[str, Any]]
    ) -> PipelineResponse:
        return PipelineResponse(
            False,
            data={"trace": trace},
            error_code=decision.code,
            error=decision.reason,
            severity=decision.severity,
            suggestions=decision.suggestions,
            evidence=decision.evidence,
        )

    def query(self, question: str) -> PipelineResponse:
        trace: list[dict[str, Any]] = []
        started = perf_counter()
        entities = extract_entities(question)
        self._trace(trace, "entities", started)

        started = perf_counter()
        question_decision = self.semantic_guard.check_question(question, entities)
        self._trace(trace, "semantic_question_guard", started, code=question_decision.code)
        if question_decision.severity in {"refuse", "clarify"}:
            return self._semantic_error(question_decision, trace)

        started = perf_counter()
        routed = route(question, entities, peak_columns=self.peak_columns)
        self._trace(trace, "route", started, intent=routed.intent, matched=bool(routed.sql))
        retrieved = []
        if not routed.sql:
            started = perf_counter()
            retrieved = self.retriever.retrieve(question, top_k=self.top_k)
            self._trace(
                trace,
                "retrieve",
                started,
                example_ids=[item.example["id"] for item in retrieved],
            )

        prior_error: str | None = None
        attempts = 1 if routed.sql else self.max_attempts
        for attempt in range(1, attempts + 1):
            source = "router" if routed.sql else "llm"
            if routed.sql:
                generated = GeneratedQuery(routed.sql, routed.params)
            else:
                started = perf_counter()
                prompt = build_prompt(
                    question,
                    corpus=self.corpus,
                    examples=retrieved,
                    data_range=self.data_range,
                    prior_error=prior_error,
                )
                try:
                    generated = parse_generated_query(self.llm.generate(prompt))
                except Exception as error:  # Adapter errors become bounded pipeline errors.
                    prior_error = f"LLM_OUTPUT_ERROR: {type(error).__name__}"
                    self._trace(trace, "generate", started, attempt=attempt, error=prior_error)
                    continue
                self._trace(trace, "generate", started, attempt=attempt)

            started = perf_counter()
            guard_result: SqlGuardResult = self.sql_guard.validate(generated.sql, generated.params)
            self._trace(
                trace,
                "sql_guard",
                started,
                attempt=attempt,
                source=source,
                code=guard_result.code,
            )
            if not guard_result.allowed:
                prior_error = f"{guard_result.code}: {guard_result.reason}"
                continue

            started = perf_counter()
            semantic = self.semantic_guard.check_sql(question, generated, entities)
            self._trace(trace, "semantic_sql_guard", started, attempt=attempt, code=semantic.code)
            if semantic.severity in {"refuse", "clarify"}:
                return self._semantic_error(semantic, trace)

            started = perf_counter()
            try:
                columns, rows = self.run_sql(generated.sql, generated.params)
            except Exception as error:
                prior_error = f"SQL_EXECUTION_ERROR: {type(error).__name__}: {error}"
                self._trace(trace, "execute", started, attempt=attempt, error=prior_error)
                continue
            self._trace(trace, "execute", started, attempt=attempt, record_count=len(rows))
            disclosures = []
            for decision in (question_decision, semantic):
                if decision.severity == "disclose":
                    disclosures.append(
                        {
                            "code": decision.code,
                            "reason": decision.reason,
                            "evidence": decision.evidence,
                        }
                    )
            return PipelineResponse(
                True,
                data={
                    "question": question,
                    "intent": routed.intent,
                    "sql": generated.sql,
                    "params": list(generated.params),
                    "columns": columns,
                    "rows": [list(row) for row in rows],
                    "record_count": len(rows),
                    "disclosures": disclosures,
                    "trace": trace,
                },
            )

        return PipelineResponse(
            False,
            data={"trace": trace},
            error_code="GENERATION_FAILED",
            error="SQL 在重試上限內未能通過驗證與執行。",
            severity="error",
            evidence={"attempts": attempts, "last_error": prior_error},
        )
