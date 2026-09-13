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

- CP-003：Phase 2 — 純函式對齊模組、歲修命名對齊與完整 `meta_pitfall`。

## CP-002 — Phase 1 SQLite 資料層

- 時間：2026-09-13 13:32 +08:00
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
