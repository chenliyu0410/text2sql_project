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

- CP-002：Phase 1 — SQLite 星狀模型、中文語意檢視、manifest 與資料品質報告。

## CP-001 — Phase 0 專案地基

- 時間：2026-09-13 13:12 +08:00
- 狀態：已完成
- 範圍：`pyproject.toml`、`uv.lock`、`Makefile`、`configs/`、`src/` 套件骨架、離線 CI、`SYSTEM_CARD.md`、`.env.example`。
- OpenAI 設定：依官方 Responses API 與模型文件預留 `OPENAI_MODEL`，線上套件放在選用 `online` extra，CI 不需 API key。
- 驗證：`uv sync --extra dev`、`ruff format --check .`、`ruff check .`、`pytest -q` 全數通過（2 passed）。
- 回退方式：回退 `feat: scaffold phase 0 project foundation` 這個 commit；不影響 CP-000 列出的使用者變更。
