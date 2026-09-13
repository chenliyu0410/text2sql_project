# PowerQuery TW API 契約

服務使用 JSON 與一致的回應 envelope。OpenAPI schema 位於 `/openapi.json`，互動式文件位於 `/docs`。除輸入格式錯誤、服務未就緒或模式設定錯誤外，Text2SQL 的業務層拒答仍使用 HTTP 200，並由 `success`、`error_code` 與 `severity` 表達結果。

## 管理員驗證與安全邊界

以下端點維持公開：

- 首頁、靜態資源、`/docs`、`/openapi.json`
- `GET /api/health`
- `GET /api/stats`
- `GET /api/examples`
- `POST /api/query`

`GET /api/admin/session` 與 `POST /api/admin/session` 用來查詢登入狀態及建立 session；其餘 `/api/runtime/*`、`/api/corpus/*`、`/api/data/*` 及 `GET /api/training-status` 都需要管理員 session。所有管理端點回應皆帶 `Cache-Control: no-store` 與 `Pragma: no-cache`。

本機展示預設帳號為 `admin`、密碼為 `PowerQuery@123`。這是公開的 demo 帳密，只允許 loopback 用戶端登入；對外部署前必須同時設定 `POWERQUERY_ADMIN_USERNAME` 與 `POWERQUERY_ADMIN_PASSWORD`。只設定其中一項、空值、過短密碼或不合法 TTL 都會拒絕啟動。可用 `POWERQUERY_ADMIN_SESSION_TTL_SECONDS` 設定 300～3600 秒的絕對有效期，預設 900 秒；`POWERQUERY_ADMIN_ALLOWED_HOSTS` 是不含 port 的逗號分隔 hostname/IP 清單。

登入成功後使用名為 `powerquery_admin_session` 的 host-only cookie：

- `HttpOnly`、`SameSite=Strict`、`Path=/api`
- HTTPS 時加上 `Secure`
- session token 與 CSRF token 都是隨機 opaque 值；伺服器端只保存 SHA-256 digest
- session 不會滑動續期，服務重啟即全部失效
- 前端不把密碼或 CSRF 寫入 Web Storage；cookie 只由瀏覽器管理，JavaScript 無法讀取

所有管理寫入都必須同時提供有效 cookie、精確同源 `Origin`，以及最新的 `X-PowerQuery-CSRF`。若送出 `Sec-Fetch-Site`，值也必須是 `same-origin`。

### `POST /api/admin/session`

建立短期管理 session。登入本身也必須帶與請求 URL 完全相同的 `Origin`。

```json
{
  "username": "admin",
  "password": "PowerQuery@123"
}
```

成功回應會以 `Set-Cookie` 設定 session，並回傳只應保存在記憶體的 CSRF：

```json
{
  "success": true,
  "data": {
    "authenticated": true,
    "username": "admin",
    "issued_at": "2026-09-13T01:00:00+00:00",
    "expires_at": "2026-09-13T01:15:00+00:00",
    "using_default_credentials": true,
    "csrf_token": "目前 session 的隨機值",
    "session_ttl_seconds": 900
  }
}
```

帳密錯誤回 401；不可信任 host、非同源或使用預設帳密從非 loopback 登入回 403；同一來源五分鐘內失敗過多回 429，並帶 `Retry-After`。錯誤不回顯帳密。

### `GET /api/admin/session`

沒有 cookie、cookie 無效或已逾期時回 HTTP 200：

```json
{
  "success": true,
  "data": {
    "authenticated": false,
    "using_default_credentials": true,
    "session_ttl_seconds": 900
  }
}
```

cookie 有效時回登入者資訊與新的 `csrf_token`。每次呼叫都會輪替 CSRF，舊值立即失效，且不延長 session 絕對有效期；頁面重新整理後應先呼叫本端點取得新值。

### `DELETE /api/admin/session`

需要 cookie、精確同源 `Origin` 與 `X-PowerQuery-CSRF`。成功後撤銷伺服器端 session、清除 cookie，並回 `authenticated: false`。

## 執行模式

`RuntimeManager` 支援：

- `offline`：規則路由與本機唯讀 SQLite，不呼叫遠端模型。
- `online`：規則未涵蓋時使用 OpenAI Responses API；需要 API key 與 online 額外依賴。
- `auto`：有可用 API key 時使用線上 runtime，否則退回離線規則。

### `GET /api/runtime/llm`

需要管理員 session。回傳安全狀態，不包含 API key：

```json
{
  "success": true,
  "data": {
    "default_mode": "auto",
    "active_mode": "offline",
    "online_configured": false,
    "provider": "openai",
    "model": "gpt-5.4-mini",
    "source": "offline",
    "offline_capability": true
  }
}
```

`source` 可能是 `offline`、`memory`、`environment` 或注入測試使用的 `injected`。

### `PUT /api/runtime/llm`

需要管理員 session、同源與 CSRF。`mode` 必填；`api_key` 與 `model` 可省略以保留現值。

```json
{
  "mode": "online",
  "api_key": "sk-…",
  "model": "gpt-5.4-mini"
}
```

由 API 提供的 key 只存在伺服器程序記憶體，狀態與稽核紀錄只記錄是否有變更，不保存或回傳 key。`api_key: null` 可清除記憶體內 key；若啟動環境仍有 `OPENAI_API_KEY`，線上憑證仍會被視為可用。設定採先建立後切換，失敗時保留原 runtime 並回 400。

## 查詢

### `POST /api/query`

公開端點。`question` 為 1～500 字；`execution_mode` 可為 `offline`、`online`、`auto` 或省略，只影響本次查詢：

```json
{
  "question": "2026年7月20日出力前五名機組",
  "execution_mode": "offline"
}
```

指定 `online` 但沒有可用憑證時回 409。成功的 `data` 包含 `sql`、`params`、`tables`、`columns`、`rows`、`record_count`、`disclosures`、`trace`、`chart_spec`、`explanation`、`statistics`，以及：

- `runtime`：本次實際使用的模式、provider 與 model。
- `learning`：語料候選觀察結果；語料工作區失敗不會把已完成查詢改成失敗。
- `data_provenance`：`database_version` 與本次 SQL 涉及的 `data_sources`。每筆來源含資料槽、顯示檔名、版本、SHA-256、大小、存在狀態與對應語意 view。

`chart_spec.kind` 只允許 `line`、`bar`、`scatter` 或 `null`，不允許 JavaScript formatter 或其他可執行內容。

業務層拒答範例：

```json
{
  "success": false,
  "error_code": "PEAK_SUM_ACROSS_DAYS",
  "error": "…",
  "severity": "refuse",
  "suggestions": ["…"],
  "evidence": {}
}
```

## 語料治理與人工審核

「學習」代表新增受治理的 Text2SQL 檢索範例，不是背景微調。規則 router 與線上 LLM 的有效候選都必須先經去識別、重複與 benchmark 洩漏檢查、SQL／語意護欄、結果重播及檢索回歸，然後一律停在 `pending_review`；不存在 router 自動發布例外。只有通過人工核准並以當下資料與語料基線重驗的候選才能成為 `promoted`。

候選位於資料庫旁的 `.powerquery-learning/`，不直接修改版控中的 `corpus/training_corpus.json`。它保存去識別問句、SQL、參數、來源、涉及資料表、驗證、結果 checksum 與 `data_provenance`，不保存查詢結果 rows。資料庫基線變更時，舊的已發布候選會回到 `pending_review` 等待重新審核。

### `GET /api/training-status`

需要管理員 session。政策欄位目前為：

```json
{
  "auto_promote_source": null,
  "manual_review_required": true,
  "router_requires_review": true,
  "llm_requires_review": true,
  "maximum_retrieval_drop": 0.0
}
```

`is_training_complete` 只表示工作區及索引已同步，不代表待審候選已被自動核准。

### `GET /api/corpus/entries`

需要管理員 session。`state` 可為 `all`、`validating`、`pending_review`、`promoted`、`rejected`、`ignored`；`limit` 為 1～500，預設 100。內容由新到舊排列，不含查詢結果 rows。

### `GET /api/corpus/events`

需要管理員 session。`limit` 為 1～500，預設 100，回傳去識別事件。

### `POST /api/corpus/entries/{candidate_id}/review`

需要管理員 session、同源與 CSRF，只接受 `pending_review`：

```json
{
  "decision": "approve",
  "note": "已核對 SQL 與資料來源"
}
```

`decision` 可為 `approve` 或 `reject`；`note` 可省略，最長 500 字。審核者一律取自 session 的 `username`，request body 不接受 `reviewer`。核准前會以目前資料庫與語料重新驗證；找不到候選回 404，狀態已改變或不可審核回 409。審核同時寫入語料事件與資料管理稽核鏈。

## 資料管理與熱插拔

資料 API 不接受任意 SQL 或使用者提供的 SQLite，只管理固定、具 schema 約束的 UTF-8 CSV：

| `dataset` | 固定檔名 | 可新增／替換 | 可移除 |
|---|---|:---:|:---:|
| `units_csv` | `units.csv` | 是 | 否 |
| `daily_csv` | `daily.csv` | 是 | 否 |
| `crosswalk_csv` | `crosswalk.csv` | 是 | 否 |
| `daily_long_csv` | `daily_long.csv` | 是 | 否 |
| `outage_csv` | `outage.csv` | 是 | 是 |

上傳、移除、回退都只建立 `pending_review` 變更。建置成功不代表發布；人工核准時才會再次驗證來源與資料庫 checksum，原子切換 runtime 與 `active.json`。若核准的候選基於已過期的 active version，回 409，必須重新建立候選。回退也建立新待審變更，不會直接切換。

### 讀取端點

下列端點都需要管理員 session：

- `GET /api/data/status`：active version/revision、資料槽、候選統計與稽核鏈狀態。
- `GET /api/data/files`：active version 的來源 manifest。
- `GET /api/data/files/{dataset}?version={version}`：下載 active 或指定已知版本的來源 CSV。`version` 請直接使用版本 API 回傳的 69 字元 ID。
- `GET /api/data/changes?state=all&limit=100`：調閱變更；`state` 可為 `all`、`pending_review`、`approved`、`rejected`、`failed`。
- `GET /api/data/changes/{change_id}`：單筆變更。
- `GET /api/data/versions?limit=100`：已發布、不可變版本。
- `GET /api/data/events?limit=100`：驗證完整 hash chain 後，回傳由新到舊的稽核事件。

所有 `limit` 都是 1～500。

### `POST /api/data/changes/upload`

需要管理員 session、同源與 CSRF。`content_base64` 可為純 base64 或帶 `;base64,` 的 data URI；解碼後上限 64 MiB。

```json
{
  "dataset": "outage_csv",
  "filename": "outage.csv",
  "content_base64": "77u/...",
  "reason": "展示更新九月歲修資料"
}
```

系統驗證 `.csv` 副檔名、UTF-8/UTF-8 BOM、NUL、標頭重複、必填欄位及至少一筆資料，再使用 deterministic builder 產生候選資料庫。`reason` 可省略，最長 500 字。

### `POST /api/data/changes/remove`

需要管理員 session、同源與 CSRF。目前只有 `outage_csv` 可移除：

```json
{
  "dataset": "outage_csv",
  "reason": "展示資料檔移除"
}
```

### `POST /api/data/changes/{change_id}/review`

需要管理員 session、同源與 CSRF：

```json
{
  "decision": "approve",
  "note": "已核對筆數與 checksum"
}
```

`decision` 可為 `approve` 或 `reject`。審核者只能來自 session，不能由 request body 指定。核准成功後，新請求立即使用新資料庫，語料服務也會依新資料基線重建。

### `POST /api/data/versions/{version}/rollback`

需要管理員 session、同源與 CSRF；目標必須是已發布且不是目前 active 的版本：

```json
{
  "reason": "展示完成，準備回到前一版"
}
```

成功只回傳 `pending_review` 候選；仍須呼叫資料變更 review 才會套用。

### 版本、檔案與稽核

工作區位於資料庫旁的 `.powerquery-data/`，包含不可變來源快照、候選／已發布資料庫、變更與版本 manifest、`active.json`、短暫的 build／mutation／publish journals、append-only `audit.jsonl`、獨立 audit head 及其永久建立標記。build journal 將候選 DB bytes/hash 綁到確切來源，mutation journal 成對提交 change 與 audit；不可變發布紀錄與核准事件會先落盤，`active.json` 才是最後 commit point。中斷後可由相應 journal 冪等恢復。稽核事件含已驗證帳號與操作細節，並以 `previous_hash`／`event_hash` 串接；audit head、active revision、版本與 checksum 會交叉驗證，偵測到來源、DB、manifest、指標或稽核遭刪改時，資料查詢與所有管理 API 都 fail closed。名稱含 `password`、`secret`、`token`、`credential` 或 `api_key` 的欄位會在寫入邊界遮罩。

## 常見狀態碼

- 400：runtime 設定或資料內容／操作參數不合法。
- 401：帳密錯誤，或需要登入的端點缺少／使用無效 session。
- 403：host、Origin、`Sec-Fetch-Site` 或 CSRF 驗證失敗；預設帳密從非 loopback 登入也屬此類。
- 404：找不到指定候選、資料變更、版本或來源。
- 409：指定線上模式不可用、候選狀態衝突、舊基線衝突或不允許的資料狀態。
- 422：JSON/schema 驗證失敗。FastAPI detail 不包含原始 `input`，避免問句或 API key 被反射。
- 429：登入嘗試受到限速。
- 503：資料庫、語料／資料工作區未就緒，或稽核鏈完整性失敗。

所有回應另附 CSP、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY` 與 `Referrer-Policy: no-referrer`。
