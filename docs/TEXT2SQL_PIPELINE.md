# Text2SQL Pipeline Contract

## 入口與輸出

`Text2SQLPipeline.query(question)` 接受一個中文問句，回傳 `PipelineResponse`。成功回應的 `data` 固定含 `question`、`intent`、`sql`、`params`、`columns`、`rows`、`record_count`、`disclosures` 與 `trace`；失敗回應使用結構化 `error_code`、`severity`、`suggestions` 與 `evidence`。

## 管線順序

1. 實體與日期抽取。
2. 問句層語意守門。
3. 規則意圖路由；無可直接執行查詢才進入 RAG。
4. 字元 n-gram TF-IDF 檢索，組合 schema、領域規則、近似範例與動態資料期間。
5. LLM 回傳 `{sql, params}`；最多按 `max_attempts` 重生。
6. 所有 SQL，包含手寫 router SQL，一律經過 AST 安全守門。
7. SQL 層語意守門。
8. 透過注入的 `run_sql` 唯讀執行，失敗才進入下一次重生。

## SQL 安全契約

- 單一 `SELECT`，不允許註解、多敘述、CTE、DDL、DML、`ATTACH`、`PRAGMA` 或危險函式。
- 資料來源只能是 `v_unit`、`v_peak`、`v_system`、`v_outage`，欄位也必須在各 view allowlist。
- 字串條件使用 `?` placeholder，`params` 數量必須一致。
- 必須有整數 `LIMIT`，上限由 `configs/guard.yaml` 決定。

## LLM adapter

`FakeLLM` 用於離線 CI 與重試測試。`OpenAILLM` 使用 OpenAI Responses API 的 JSON Schema Structured Outputs；需安裝 `online` extra，而且必須有 `OPENAI_API_KEY`。缺 key 時明確報錯，不會自動 fallback。

## Trace

每步記錄 `stage`、`elapsed_ms` 及必要的 `attempt`、`code` 或 `record_count`。Trace 不記錄完整 prompt、API key 或 stack trace。
