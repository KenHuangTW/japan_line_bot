## Context

目前旅次顯示層已經有兩個主要入口：`/清單` 回 LINE Flex carousel，`/trips/{display_token}` 回 server-rendered HTML。資料層也已在 `TripDisplayLodging` 帶出 `hero_image_url` 與 `line_hero_image_url`，其中 LINE Flex 已使用 `line_hero_image_url` 做住宿卡片 hero image；但 HTML detail page 的 `_build_lodging_cards()` 只渲染文字、chips、連結與決策按鈕，沒有圖片。

這次變更應該集中在 rendering 與測試，不需要新增資料欄位，也不需要改 map enrichment 或 Notion sync。目標是讓使用者從 LINE preview 點進完整網頁時，仍能靠縮圖快速對照同一批住宿。

## Goals / Non-Goals

**Goals:**
- 在旅次詳情頁每張住宿卡片中顯示可點擊或可辨識的住宿縮圖
- 重用 canonical lodging image metadata，避免重新抓圖或新增圖片同步流程
- 讓無圖房源維持穩定 fallback，不能因缺圖造成排版破裂或空白區塊
- 補強 HTML rendering regression tests，涵蓋圖片 escaping、fallback 與既有文字資訊共存

**Non-Goals:**
- 不新增圖片 proxy、快取服務或背景抓圖 job
- 不改變 `/清單` 的 LINE Flex payload 格式
- 不新增前端框架或 template engine
- 不解決外站圖片 hotlink 失敗、CORS、403 等平台政策問題；第一版只使用已存在的圖片 URL

## Decisions

### 1. 網頁優先使用 `hero_image_url`，必要時 fallback 到 `line_hero_image_url`

HTML 頁面面向瀏覽器，不受 LINE image 格式限制，因此卡片縮圖優先採用原始 `hero_image_url`。若原始欄位缺失但已有 `line_hero_image_url`，則 fallback 使用 LINE-compatible URL。這讓網頁能呈現較完整的平台圖片，同時保留現有 normalized image 的備援價值。

Alternatives considered:
- 只使用 `line_hero_image_url`
  - Rejected: 這會把 LINE 的格式限制套到網頁，且可能丟失瀏覽器可正常顯示的原始圖片。
- 重新從住宿 URL 抓圖
  - Rejected: 圖片資料已在 enrichment 流程中取得，頁面 render 不應觸發外部網路副作用。

### 2. 在 HTML rendering 層組裝縮圖 markup，不改變 repository model

`TripDisplayLodging` 已包含需要的圖片欄位，因此只在 `app/trip_display/rendering.py` 增加 card media markup 與 CSS。repository 與 API payload 不需要為這次變更新增欄位。

Alternatives considered:
- 新增 `thumbnail_url` model property
  - Rejected: 若只是單一 rendering decision，先用 rendering helper 集中處理即可；等多個 surface 需要相同策略時再抽共用 property。
- 改用 Jinja template
  - Rejected: 目前 HTML 是單檔 string renderer，這次改動範圍小，先維持既有模式。

### 3. 無圖房源使用固定尺寸 fallback，而不是省略 media 區塊

卡片應保留穩定尺寸與資訊層級：有圖時顯示 `<img>`，無圖時顯示平台與狀態文字 fallback。這能避免列表中有些卡片高度大幅跳動，也讓使用者知道缺圖是資料狀態而不是頁面壞掉。

Alternatives considered:
- 無圖時完全不顯示圖片區
  - Rejected: 混合有圖與無圖卡片會讓列表掃描體驗不一致。
- 使用外部 placeholder service
  - Rejected: 會新增不必要外部依賴。

### 4. 圖片 URL 與 alt text 必須走 HTML escaping

所有 `src`、`href`、`alt` 與文字 fallback 都必須使用既有 `html.escape` pattern。縮圖本身可以連到原始住宿頁，但不能讓住宿名稱或圖片 URL 注入 HTML attribute。

Alternatives considered:
- 直接插入 URL / title
  - Rejected: trip display link 是可公開分享的 read-only surface，rendering 必須維持基本 escaping。

## Risks / Trade-offs

- [外站圖片可能禁止 hotlink 或回傳不適合尺寸] -> 使用固定 aspect-ratio 與 `object-fit: cover`，圖片失敗時仍保留文字內容與原始連結。
- [HTML string renderer 持續變長] -> 將 thumbnail markup 拆成小 helper，避免 `_build_lodging_cards()` 過度膨脹。
- [無圖 fallback 可能讓頁面看起來像假的圖片] -> fallback 以平台與「沒有縮圖」資訊為主，不假裝成實際房源圖片。
- [桌面版卡片可能變得太高] -> 使用 responsive layout，手機直向堆疊，桌面可採 media + content 的橫向或固定比例排列。

## Migration Plan

1. 在 `rendering.py` 增加縮圖 URL 選擇 helper、HTML markup 與 CSS。
2. 更新住宿卡片 markup，確保縮圖、文字資訊、links 與 decision forms 同時存在。
3. 補上 rendering / route tests，驗證有圖、無圖與 escaping。
4. 更新 README 中旅次頁描述，說明網頁詳情頁也會顯示住宿縮圖。

Rollback strategy:
- 移除 thumbnail helper、CSS 與 card media markup 即可回到純文字卡片；不涉及資料 migration。

## Open Questions

- 桌面版第一版要採「上圖下文」還是「左圖右文」？實作時可依現有頁面寬度與測試快照選擇較穩定的 responsive layout。
- 圖片載入失敗時是否需要 client-side fallback script？第一版建議不要，除非實測外站圖片失敗比例很高。
