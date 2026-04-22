## Why

`/清單` 的 LINE Flex 卡片已經能用住宿主圖快速辨識房源，但旅次網頁仍是純文字卡片，使用者從 LINE 點進完整清單後反而失去縮圖脈絡。現在 canonical lodging data 已有 `hero_image_url` / `line_hero_image_url`，適合把同一份圖片資料延伸到網頁顯示層。

## What Changes

- 讓 `/trips/{display_token}` 旅次詳情頁的住宿卡片顯示縮圖，視覺行為與 `/清單` 的 LINE preview 保持一致。
- 網頁縮圖優先使用已正規化、可瀏覽器顯示的住宿圖片欄位，並在沒有圖片時提供穩定的文字 fallback，不阻斷卡片渲染。
- 調整旅次詳情頁的 mobile-first 版面，確保縮圖、名稱、chips、連結與決策按鈕在手機與桌面都不互相擠壓。
- 補上 HTML rendering / route regression tests，驗證有圖、無圖與特殊字元 escaping 情境。

## Capabilities

### New Capabilities
- `trip-webpage-thumbnails`: 旅次網頁詳情頁 SHALL 使用 canonical lodging image metadata 呈現住宿縮圖，並在圖片缺失時保留可讀的文字卡片。

### Modified Capabilities
- None.

## Impact

- Affected code: `app/trip_display/rendering.py`, `tests/test_webhook.py`, `tests/test_trip_display.py`, `README.md`
- Data/API: 不新增資料欄位；重用既有 `hero_image_url` / `line_hero_image_url` 與 trip display payload
- Dependencies/systems: 不引入前端框架或外部圖片 proxy；沿用 server-rendered HTML 與現有 map enrichment image extraction
