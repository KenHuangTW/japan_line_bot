## Why

目前旅次詳情頁已能顯示住宿清單，但視覺風格仍偏一般後台卡片，和使用者期待的「旅程記錄」感不一致。現在已有住宿縮圖、決策狀態與旅次統計資料，適合把頁面整理成更像紙本文書的可分享瀏覽介面，讓 `/清單` 打開後能直接進入清楚、安靜、可比較的住宿 review 流程。

## What Changes

- 將旅次詳情頁改為參考 `/Users/ken/Downloads/Trip _.html` 的 trip log 風格：窄版置中、米白紙感底色、細黑頂線、serif 大標題、mono eyebrow / 編號、淡邊框統計格與低彩度 lodging rows。
- 將目前的大型 rounded card / gradient hero / pill chips 轉為更克制的文書式版面，讓內容、縮圖、狀態與操作更像清單紀錄而不是 dashboard。
- 保留現有 server-rendered FastAPI HTML，不引入 React、SPA 或前端 build pipeline。
- 重新安排篩選、排序、統計與 actions，確保 mobile-first 使用時可讀、可點擊，且不遮擋住宿標題與縮圖。
- 讓 lodging item 使用穩定 row 結構：序號、平台、決策狀態、住宿縮圖或 fallback、標題、地點/收錄時間、價格/可訂狀態、原始連結、地圖、Notion、決策表單。
- 補上 HTML rendering 測試，避免後續改版遺失核心樣式 class、統計文字、縮圖 fallback 與決策 controls。

## Capabilities

### New Capabilities
- `trip-display-visual-style`: Defines the visual style, layout, responsive behavior, and rendering expectations for the trip detail surface.

### Modified Capabilities
- None.

## Impact

- Affected code: `app/trip_display/rendering.py`, `tests/test_trip_display.py`, possibly `README.md` if screenshots or operator notes are added later.
- Data/API: No storage or API contract changes expected; this is a server-rendered HTML presentation change over the existing `TripDisplaySurface` payload.
- UX: The trip detail page becomes a document-like lodging review page with clearer hierarchy, calmer colors, and tighter mobile layout.
- Dependencies/systems: No new runtime dependency; external web fonts should not be required for the first implementation because the existing server-rendered page should remain fast and self-contained.
