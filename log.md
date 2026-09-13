# PowerQuery TW 開發進度

> 這份檔案在每個可驗證、可回退的儲存點更新。回退前需保留使用者原有的未提交變更。

## CP-000 — 實作前基線

- 時間：2026-09-13 13:02 +08:00
- 狀態：已完成
- Git 基線：`4565ca08adbb2a3d413c4d94283a1a3a9e67a2c8`
- 已驗證：`taipower_align/align.py` 與 `taipower_align/final.py` 都可在 Python 3.13 成功執行。
- 現有資料基準：175 台機組、577 天、43 個已對應欄位、36,928 筆長表資料。
- 使用者原有未提交變更：`.gitignore`、`README.md`、系統規格、`docs/AI_AGENT_COLLABORATION.md`、`scripts/`、`參考資料/`。
- 回退方式：只回退 CP-001 之後新增的實作檔；不對上述使用者變更執行 reset 或 checkout。

## 進行中

- 無。README 與系統規格定義的 Phase 0～7 已完成；線上 LLM 實測仍需有效的 `OPENAI_API_KEY`，不影響離線規則模式與 E2E 驗收。

## CP-008 — Phase 7 API、CLI 與對話式呈現層

- 時間：2026-09-13 14:23 +08:00
- 狀態：已完成
- API：完成 FastAPI 應用、延遲載入 runtime、健康／資料統計／語料狀態／範例／查詢端點與 OpenAPI 文件；資料庫未就緒時回 503，輸入格式錯誤回 422，語意拒答維持結構化業務 envelope。
- CLI：`powerquery` 可直接查詢、輸出完整 `--json`，或以 `--serve` 啟動 Uvicorn；`make serve` 與 `SERVING.md` 收錄可重現操作方式。
- 呈現：後端只建立 `line`、`bar`、`scatter` 白名單圖表規格，日期／數值、類別／數值與雙數值形狀各自選圖；scalar、空結果、全 NULL 或純文字回傳 `chart_spec: null`。圖表 x/y 直接投影自 SQL rows。
- 前端：完成繁中對話介面、資料涵蓋側欄、範例問句、階段式進度、可取消查詢、結構化錯誤／限制揭露、KPI、表格、SQL 細節與響應式版面。固定版本 Plotly.js basic bundle提供互動圖表，無法載入 CDN 時退回相同資料的原生 SVG。
- 安全與無障礙：所有動態內容使用 `textContent` 或 SVG attribute，不拼接不可信 HTML；加入 CSP、`nosniff`、frame deny 與 no-referrer headers；支援雙 live region、`aria-current`、鍵盤焦點、中文輸入法組字、防誤送 Enter、reduced motion 與手機 safe area。
- 相依版本：FastAPI 0.141.1、Uvicorn 0.52.4、HTTPX2 2.12.0；Plotly.js basic bundle 固定為 4.0.0 並驗證 SHA-384 SRI。
- 實機驗收：本機 Uvicorn 啟動後，`GET /api/health` 與 `POST /api/query` 均回 200；「2026年6月每日備轉容量率」取得 30 筆，`chart_spec.data[0].x[0]` 與 SQL 第一列日期同為 `2026-06-01`。
- CLI 驗收：「2026年7月備轉容量率最低是哪一天？」成功回傳 `2026-07-05`、`10.23%`；無 API key 時明確標示離線規則模式，長尾問題不以假模型輸出替代。
- 自動驗收：`ruff format --check .`、`ruff check .`、`node --check src/serving/static/app.js`、`pytest -q` 全數通過（65 passed）。Starlette 1.6.0 仍從第三方 `testclient.py` 發出一則 AnyIO 型別別名淘汰警告，不影響測試或執行。
- 回退方式：回退 `feat: deliver api cli and accessible web interface` 這個 commit；CP-001～007 與使用者原有變更保持不動。

## CP-007 — Phase 6 離線評測與回歸關卡

- 時間：2026-09-13 14:09 +08:00
- 狀態：已完成
- 結果比對：候選 SQL 與標準 SQL 都在同一個唯讀 SQLite 快照上執行；指標以欄名集合與列集合等價性計算，不比對 SQL 字串。
- 離線基準：黃金意圖 80/80；eval 意圖 60/60；執行結果 60/60，`in_corpus=true` 與 `false` 各 30/30；攻擊 15/15；語意陷阡 45/45；合法邊界題 0/20 誤攔。所有驗收條件通過。
- 詮釋界線：上述執行成績標示為 `offline_deterministic_rules`，是可重現規則 handler 基準，不是線上 GPT 準確率；沒有 API key 時不會把 benchmark 答案假裝成 LLM 輸出。
- Ablation：RAG top-1 意圖為 31/60（51.67%），無檢索且預設 other 為 6/60（10%）；語意守門開／關陷阡處理為 100% / 0%；規則查詢首次已成功，重試 1/2/3 次無差異；關閉路由的對照需線上 LLM，誠實標記 `not_run_without_online_llm`。
- 語料回歸：`CorpusRegressionGate` 比較候選 corpus 與基線的獨立題庫 top-1 意圖檢索率，超過可容忍退步就拒絕整批晉升。
- 產物：`reports/eval_latest.json`、只追加的 `reports/eval_history.jsonl`、`reports/figures/eval_summary.svg`；`make eval` 可重建。
- 驗收：`python -m eval.run_eval`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（57 passed）。
- 回退方式：回退 `feat: add reproducible offline evaluation` 這個 commit；CP-001～006 與使用者原有變更保持不動。

## CP-006 — Phase 5 資料語意守門

- 時間：2026-09-13 13:52 +08:00
- 狀態：已完成
- 雙層判斷：在生成前檢查問句可答性，在執行前再以 `sqlglot` AST 檢查真實 SQL 形狀；所有結果都是結構化 `code`、`severity`、說明、建議與 evidence。
- 規則：完成 `PEAK_SUM_ACROSS_DAYS`、`UNIT_MISMATCH`、`NO_UNIT_DETAIL`、`RESIDUAL_TREND`、`PLANT_TOTAL_INCOMPLETE`、`KNOWN_CAPACITY_GAP`、`ZERO_PERIOD_AMBIGUOUS`、`AMBIGUOUS_UNIT_NAME`、`DATA_RANGE_OUT_OF_BOUNDS` 九條守門。
- 分級：`refuse` 與 `clarify` 不執行 SQL；`disclose` 可繼續查詢但必須隨結果回傳限制。同一規則在問句層與 SQL 層同時命中時只揭露一次。
- 動態資料：資料期間從 `meta_manifest` 讀取；殘差欄、電廠總量不完整與容量缺口對象從 `meta_pitfall` 讀取，查詢層不重複寫死清單。
- 邊界檢查：單日跨機組加總、同單位容量比較、殘差欄單日值、具明確期間的零出力等 20 個反例均放行。
- 驗收：陷阡題 45/45 命中（100%，要求 ≥ 95%）；20 個合法邊界反例 0 誤攔（0%，要求 ≤ 5%）；`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（52 passed）。
- 回退方式：回退 `feat: add data-aware semantic guardrails` 這個 commit；CP-001～005 與使用者原有變更保持不動。

## CP-005 — Phase 4 Text2SQL 管線

- 時間：2026-09-13 13:44 +08:00
- 狀態：已完成
- 管線：建立實體抽取→問句語意接點→零成本路由→字元 n-gram TF-IDF 檢索→LLM結構化產生→SQL AST 守門→SQL語意接點→唯讀 SQLite 執行的完整編排，並在 trace 保留每步驟耗時。
- 實體：支援西元日期、民國年、中文／全形數字、去年／今年／上個月／上下半年、燃料與 Top-N；相對日期可注入 reference date 以便重現。
- 線上／離線：`OpenAILLM` 使用 Responses API 與 JSON Schema Structured Outputs；`FakeLLM` 用於無 key 的離線 CI，線上模式缺 key 時明確報錯，不會假裝成真實模型。
- 安全：所有路由與 LLM SQL 都經過同一守門；只允許單一 `SELECT`、四個審核 view 與欄位 allowlist，強制參數化字串、`LIMIT <= 200`，禁止註解、多敘述、寫入、系統表與危險函式。SQLite adapter 以 `mode=ro`、`query_only` 與 progress handler 做唯讀及逾時防護。
- 失敗處理：LLM 輸出、SQL 守門或執行錯誤會帶結構化原因重生，上限 3 次；仍失敗時回傳 `GENERATION_FAILED`，不偷換預設查詢。
- 驗收：黃金意圖題庫 80/80（100%，要求 ≥ 90%）；攻擊題庫 15/15 全數攔截；`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（42 passed）。
- 回退方式：回退 `feat: implement guarded text2sql pipeline` 這個 commit；CP-001～004 與使用者原有變更保持不動。

## CP-004 — Phase 3 語料與獨立題庫

- 時間：2026-09-13 13:31 +08:00
- 狀態：已完成
- 正式語料：`corpus/training_corpus.json` 含 DDL、領域文件與 40 組 question–SQL examples；已建立可重現的字元 n-gram `corpus/index.json`。
- 題庫：`golden_questions.json` 80 題（10 意圖各 8 題）、`eval_questions.json` 60 題（`in_corpus=true/false` 各 30）、`trap_questions.json` 45 題（9 條規則各 5）、`attack_questions.json` 15 題。
- 訓練／測試邊界：corpus 與所有 benchmark 問句正規化後無逐字重疊；benchmark 不會被索引。
- 自動語料學習：加入去識別、批次去重、benchmark 洩漏阻擋、可注入 SQL／語意／結果關卡、回歸關卡、版本 checksum、舊版備份與 rollback。
- 原子性：一個 batch 中任一候選失敗時，正式 corpus 與 index 都不會被部分更新。
- 驗證：`python -m text2sql.corpus`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（23 passed）。
- 回退方式：回退 `feat: add governed corpus and isolated benchmarks` 這個 commit；已發布的 corpus 也可用 `rollback_corpus` 切回 `corpus/versions/` 備份。

## CP-003 — Phase 2 對齊層與歲修資料

- 時間：2026-09-13 13:24 +08:00
- 狀態：已完成
- 範圍：命名轉換、粒度／燃料分類、crosswalk 容量比驗證、歲修對齊、從對齊結果產生 `meta_pitfall`，所有核心郏輯都是無資料庫、無網路 I/O 的純函式。
- Crosswalk：43 列唯一對應、175 台機組全數涵蓋，ratio 重算與異常備註檢查無 issue。
- 歲修快照：官方 `d006008` 138 列已以內容 SHA-256 `f0b30c1d32a3…` 封存。自動對齊 125 列（90.58%），達成 ≥ 90% 驗收門檻。
- 未對齊：`大潭#8`、`大潭#9`、`興達新#1` 不存在目前機組主檔；`立霧` 可指向兩台機組。全數留在 `reports/outage_unmatched.txt` 供人工核對，沒有猜測。
- 下載問題與修正：Python 3.13 系統 CA 第一次拒絕官方端點的舊憑證鏈。改用 `certifi` 信任 CA bundle 後通過，未關閉 TLS 驗證。
- 官方資料警告：歲修第 102 列的開始日 `2027-12-20` 晚於結束日 `2027-02-23`。系統保留原值、設 `date_status=invalid_range`，不自行猜測正確年份。
- 資料陷阱：`meta_pitfall` 共 10 列：`RESIDUAL_TREND` 2、`PLANT_TOTAL_INCOMPLETE` 6、`KNOWN_CAPACITY_GAP` 2。
- 驗證：`python -m align`、重建 `power.db`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（15 passed）。
- 回退方式：回退 `feat: extract alignment layer and import outages` 這個 commit；CP-001／002 保持不動。

## CP-002 — Phase 1 SQLite 資料層

- 時間：2026-09-13 13:18 +08:00
- 狀態：已完成
- 範圍：資料下載與內容尋址封存、CSV schema／日期／數值／重複鍵驗證、SQLite 星狀模型、四個 `v_*` 語意檢視、`meta_manifest`、資料字典與品質報告。
- 驗收數字：22 座電廠、175 台機組、64 個原始出力欄位、43 個主檔對應、36,928 筆尖峰出力、577 筆系統日資料。
- 資料期間：2025-01-01 ～ 2026-07-31；來源檔、建庫內容與 schema 都有 checksum，重建內容冪等。
- Schema 決策：增加 `dim_b_column` 保留全部 64 欄，`bridge_b_column` 專注 43 個已對應關係，避免 B-only 的 21 欄在 fact 裡丟失。
- 資料異常與修正：52 台機組的商轉日期只有月精度（`YYYYMM`）。系統保留原值與 `month` 精度，並以當月 1 日作可排序值，沒有偽造不存在的精確日期。
- 資料陷阱：建庫時由 crosswalk 導出 2 個殘差趨勢、6 個電廠總量不完整、2 個容量缺口，共 10 列，沒有寫死對象清單。
- 驗證：`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（7 passed）；SQLite `quick_check=ok`，四個 views 齊全。
- 產物：`data/processed/power.db` 為可重建、gitignored 產物；`reports/data_quality.json` 保留本次驗證結果。
- 回退方式：回退 `feat: build validated SQLite semantic layer` 這個 commit；Phase 0 與使用者原有變更保持不動。

## CP-001 — Phase 0 專案地基

- 時間：2026-09-13 13:12 +08:00
- 狀態：已完成
- 範圍：`pyproject.toml`、`uv.lock`、`Makefile`、`configs/`、`src/` 套件骨架、離線 CI、`SYSTEM_CARD.md`、`.env.example`。
- OpenAI 設定：依官方 Responses API 與模型文件預留 `OPENAI_MODEL`，線上套件放在選用 `online` extra，CI 不需 API key。
- 驗證：`uv sync --extra dev`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（2 passed）。
- 回退方式：回退 `feat: scaffold phase 0 project foundation` 這個 commit；不影響 CP-000 列出的使用者變更。
