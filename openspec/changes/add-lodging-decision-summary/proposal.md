## Why

目前系統能收錄與同步住宿房源，但在真正討論前，使用者仍要自己整理候選名單、優缺點與缺漏資訊。若沒有一個可重複使用的決策摘要流程，使用者在每次討論前都要手動掃 Notion，效率仍然很差。

## What Changes

- 新增旅次導向的 AI 決策摘要能力，讓使用者可以針對目前旅次請求候選住宿統整。
- 將摘要輸入限定為結構化房源欄位，而不是原始 LINE 對話或 Notion 頁面全文。
- 使用結構化輸出 schema 驗證 AI 回傳結果，再轉為適合 LINE 閱讀的摘要訊息。
- 補上 Gemini 設定、失敗處理與測試，覆蓋空旅次、AI 失敗與成功摘要情境。

## Capabilities

### New Capabilities
- `lodging-decision-summary`: 支援根據旅次中的房源資料產生結構化決策摘要，提供候選住宿、優缺點、缺漏資訊與討論重點。

### Modified Capabilities
- None.

## Impact

- Affected code: `app/controllers/line_webhook_controller.py`, `app/config.py`, `app/models/*`, `app/schemas/*`, `tests/*`, `README.md`
- Data/API: 新增摘要指令、Gemini 設定與 AI 摘要 request/response schema
- Dependencies/systems: 新增 Gemini Developer API 作為外部依賴；此 change 依賴旅次 context 已經存在，才能解析 active trip 資料範圍
