# API Contract

## Endpoints

- `GET /api/health` 回傳服務狀態、是否為無 API key 的離線規則模式，以及資料期間。
- `GET /api/stats` 回傳尖峰事實列數、機組數、歲修列數與資料期間。
- `GET /api/training-status` 回傳語料索引狀態。
- `GET /api/examples` 回傳已審核的範例問句。
- `POST /api/query` 接受 `{"question": "..."}`，長度 1～500 字。

HTTP 傳輸成功但業務層拒答時仍回 200，使用結構化 envelope：

```json
{"success": false, "error_code": "PEAK_SUM_ACROSS_DAYS", "error": "…", "severity": "refuse", "suggestions": ["…"], "evidence": {}}
```

成功的 `data` 包含 `sql`、`params`、`columns`、`rows`、`record_count`、`disclosures`、`trace`、`chart_spec`、`explanation` 與 `statistics`。`chart_spec.kind` 只能是 `line`、`bar`、`scatter` 或 `null`；`data` 與 `layout` 是 Plotly 可接受的受限子集，x/y 數列直接由 SQL rows 投影，不允許 JavaScript formatter 或其他可執行內容。前端再次套用白名單後才交給 Plotly；載入不到 Plotly CDN 時會以相同 x/y 資料退回原生 SVG。

格式錯誤（空問題、超過 500 字、非 JSON）使用 FastAPI 的 422；資料庫未建立使用 503。所有回應附加 CSP、`nosniff`、`DENY` frame 與 no-referrer headers。
