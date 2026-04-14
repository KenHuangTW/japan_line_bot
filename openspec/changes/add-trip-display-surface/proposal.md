## Why

目前旅次資料雖然已經進入 Mongo 與 Notion，但使用者真正瀏覽候選房源時仍卡在兩個極端：LINE 純文字不夠好讀，Notion 表格又太依賴固定 schema，導致每次欄位演進都要承擔 migration 成本。若不把「儲存」與「顯示」拆開，後續再加 AI 摘要或 refresh，只會讓 Notion 承受更多本來不該由它負責的產品責任。

## What Changes

- 新增輕量旅次顯示層，讓使用者可以從 active trip 直接查看候選房源，而不是把 Notion 當成主要瀏覽介面。
- 調整 `/清單`，改為回傳適合 LINE 閱讀的 rich preview，並附上可開啟的旅次詳情頁連結。
- 新增以 Mongo 為資料來源的只讀旅次頁，支援手機瀏覽、基本排序與篩選，不依賴 Notion target 是否存在。
- 將 Notion 明確定位為可選匯出與手動維護入口，而非主要清單顯示層。
- 預留與旅次 AI 摘要整合的資料出口，但不在這個 change 中直接實作摘要模型。

## Capabilities

### New Capabilities
- `trip-display-surface`: 支援以 active trip 為單位提供可讀性更高的 LINE 預覽與只讀旅次頁，直接從 Mongo 資料顯示候選住宿。

### Modified Capabilities
- None.

## Impact

- Affected code: `app/controllers/line_webhook_controller.py`, `app/routers/*`, `app/controllers/*`, `app/models/*`, `app/schemas/*`, `tests/*`, `README.md`
- Data/API: 可能新增旅次顯示用 token / URL、旅次頁 API 或 HTML route、`/清單` 的 LINE 回覆格式
- Dependencies/systems: 不引入完整 SPA；優先使用既有 FastAPI 能力與 LINE rich message，並與後續 `add-lodging-decision-summary` change 保持相容
