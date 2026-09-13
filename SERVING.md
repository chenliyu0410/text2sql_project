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

也可直接從命令列查詢，或取得完整 JSON envelope：

```bash
uv run powerquery "2026年7月備轉容量率最低是哪一天？"
uv run powerquery --json "天然氣機組共有幾台？"
```

## 線上與離線模式

沒有 `OPENAI_API_KEY` 時，已審核的常見意圖會由可重現的規則路由處理；長尾問題會明確回報模型未啟用，不會用假的模型結果冒充答案。需要線上長尾生成時：

```bash
uv sync --extra online
```

接著依 `.env.example` 設定 `OPENAI_API_KEY` 與選用的 `OPENAI_MODEL`。應用程式只從環境變數讀取 key，不會把 key 寫入資料庫或前端。

## 介面與安全邊界

- API 契約見 `src/serving/API_CONTRACT.md`，互動式 OpenAPI 文件位於 `/docs`。
- 後端只允許受限的 `line`、`bar`、`scatter` 圖表資料；x/y 值直接投影自 SQL rows。
- 前端以固定版本 Plotly.js basic bundle 呈現互動圖表；網路不可用時自動退回同資料的原生 SVG。
- 瀏覽器的取消按鈕會停止等待與顯示結果，但不會中止已在伺服器端執行的工作。
- 網頁預設只綁定 `127.0.0.1`。若以 `--host 0.0.0.0` 對外提供服務，應另行配置 TLS、身分驗證與反向代理。
