# PowerQuery TW 使用方式

## 啟動

首次使用先安裝依賴並建立可重現的 SQLite 快照：

```bash
make setup
make db
```

啟動本機網頁後開啟 <http://127.0.0.1:8000>：

```bash
make serve
```

Windows 重新建置 `data/processed/power.db` 前，請先在執行服務的視窗按 `Ctrl+C` 停止服務。SQLite 檔案仍被服務、資料庫檢視器或同步程式開啟時，Windows 不允許原子替換；建庫指令會保留原本資料庫、嘗試清理暫存檔，並顯示可操作的錯誤訊息。

也可直接從命令列查詢，或取得完整 JSON envelope：

```bash
uv run powerquery "2026年7月備轉容量率最低是哪一天？"
uv run powerquery --json "天然氣機組共有幾台？"
```

## 網頁工作台

左側導覽不只提供查詢，也包含五個可切換工作區：

- **查詢中心**：自然語言查詢、單次執行模式、常用問題與僅保存非敏感問句的本機歷史。
- **資料總覽**：資料期間、尖峰紀錄、機組與歲修筆數，以及主題式分析入口。
- **語料中心**：自動學習狀態、候選內容、事件紀錄、搜尋／篩選與 LLM 候選人工審核。
- **API 與模型**：設定 `offline`、`online`、`auto`、模型與記憶體內 API key，也可清除 key 並切回離線。
- **API 文件**：本機端點與 request 範例；完整 schema 另見 `/openapi.json`。

手機版導覽具備焦點鎖定與畫面外隱藏；圖表 CDN 無法載入時會使用本機 SVG 呈現，不會再顯示撐大的空白圖示。

## 離線、線上與自動模式

服務的 RuntimeManager 可在執行期間切換三種模式：

- `offline` 只使用已審核的規則路由與本機唯讀 SQLite，完全不呼叫遠端模型。這是可重現的離線查詢能力，不是本機生成式模型；規則未涵蓋的長尾問題會清楚拒答。
- `online` 保留同一套 SQL 與語意護欄，並在規則未涵蓋時使用 OpenAI Responses API。
- `auto` 有 API key 時使用線上 runtime，否則自動退回離線模式。

純離線使用不需要 OpenAI 套件或 API key。若要啟用線上模式，先安裝選用依賴：

```bash
uv sync --extra online
```

API key 可用兩種方式提供：

1. 啟動程序前設定 `OPENAI_API_KEY`，並可選擇設定 `OPENAI_MODEL`。
2. 在網頁的 API／模型設定或 `PUT /api/runtime/llm` 輸入；這個 key 只存在伺服器程序記憶體，重啟即失效。

應用程式不會把經設定端點收到的 key 寫入磁碟、查詢紀錄或語料，狀態 API 也只回傳 `online_configured`，不回傳 key。線上 adapter 使用 [OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)，並以 `store=false` 要求不將 response 保存供日後 API 取回。

可用下列本機 API 切換預設模式；更新失敗時會保留上一個可用設定：

```bash
curl.exe -X PUT http://127.0.0.1:8000/api/runtime/llm \
  -H "Content-Type: application/json" \
  -d '{"mode":"online","api_key":"sk-…","model":"gpt-5.4-mini"}'
```

查看不含憑證的目前狀態：

```bash
curl.exe http://127.0.0.1:8000/api/runtime/llm
```

單次查詢可傳 `execution_mode` 覆寫模式，不會改變預設設定：

```json
{
  "question": "2026年7月20日出力前五名機組",
  "execution_mode": "offline"
}
```

## 自動語料學習

每次透過 Web/API 成功完成的查詢都會交給隔離的語料學習服務評估。這裡的「學習」是新增 Text2SQL 檢索範例，不是背景微調模型：

- 規則路由產生的確定性結果，在通過 benchmark 洩漏、重複、SQL／語意、結果重播與檢索回歸檢查後會自動發布，並即時重載檢索語料。
- 線上模型產生的內容只會成為 `pending_review` 候選，避免把語意上可疑但可執行的 SQL 自動當成標準答案。
- 失敗或拒答不加入候選；語料寫入失敗也不會遮蔽已成功的查詢結果。
- 工作區位於 SQLite 資料庫旁的 `.powerquery-learning/`，不會直接覆寫版控中的 canonical corpus；跨執行緒／程序寫入會共用鎖。
- 工作區 manifest 會追蹤 canonical corpus 與資料庫版本。任一基線變更時，舊 active corpus 先備份、索引重建，舊已發布候選回到 `pending_review` 重新驗證。
- 候選只保存去識別的問句、SQL、參數、來源、驗證資訊與結果 checksum，不保存查詢結果 rows。Email、token、台灣身分證、電話、長帳號與明確標示的姓名會遮罩；敏感 SQL／參數不會發布。
- 相同問題的已發布版本保持冪等；先前待審、拒絕或忽略的內容若 SQL／來源／意圖修正，可建立帶 `revision_of` 的新 revision。

前端的語料中心可調閱這些內容；API 對應如下：

- `GET /api/training-status`：語料版本、checksum、索引同步狀態、各狀態數量與發布政策。
- `GET /api/corpus/entries?state=all&limit=100`：候選內容，可依 `validating`、`pending_review`、`promoted`、`rejected`、`ignored` 篩選。
- `GET /api/corpus/events?limit=100`：語料處理事件。
- `POST /api/corpus/entries/{id}/review`：本機人員核准並重新驗證，或拒絕待審候選。

## 介面與安全邊界

- 完整 API 契約見 `src/serving/API_CONTRACT.md`；`/openapi.json` 完全由本機提供。`/docs` 互動檢視器以 nonce CSP、固定版號與 SRI 載入 Swagger UI，第一次載入該檢視器需要可連至 jsDelivr；主工作台內建的 API 文件不需要這項 CDN。
- 後端只允許受限的 `line`、`bar`、`scatter` 圖表資料；x/y 值直接投影自 SQL rows。
- 前端以固定版本 Plotly.js basic bundle 呈現互動圖表；網路不可用時自動退回同資料的原生 SVG。
- 瀏覽器的取消按鈕會停止等待與顯示結果，但不會中止已在伺服器端執行的工作。
- 網頁預設只綁定 `127.0.0.1`。若以 `--host 0.0.0.0` 對外提供服務，應另行配置 TLS、身分驗證與反向代理；記憶體內 API key 不等同於 API 身分驗證。
