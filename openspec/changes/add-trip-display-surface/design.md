## Context

目前系統的 canonical data 已經在 Mongo，LINE 只是輸入媒介，Notion 則是同步出去的表格。然而使用者實際瀏覽候選房源時，仍被迫在 LINE 純文字與 Notion 表格之間切換。這使得資料展示被 Notion schema 綁住，也讓 `/清單` 與後續 AI 摘要都建立在一個不穩定的顯示層上。

現況沒有任何 web UI 或 template 基礎，因此這個 change 需要刻意避開「做一個完整前端產品」的方向，改以最小可用的顯示層解決閱讀與分享問題。

## Goals / Non-Goals

**Goals:**
- 提供比 LINE 文字更清楚、比 Notion schema 更穩定的旅次顯示方式
- 讓 `/清單` 先回 rich preview，再引導到同一旅次的詳情頁
- 讓旅次詳情頁直接讀 Mongo，不依賴 Notion target 或 Notion schema
- 保留未來串接 AI 決策摘要的資料出口與畫面整合點

**Non-Goals:**
- 不建立完整 SPA、管理後台或登入系統
- 不把住宿編輯流程搬到 web 頁面
- 不在這個 change 中實作新的 AI provider 或摘要指令
- 不移除 Notion export 能力，只是降低它作為主顯示層的責任

## Decisions

### 1. 以 server-rendered 只讀旅次頁取代完整前端框架

新增一個 mobile-first 的只讀旅次頁，由 FastAPI 直接渲染 HTML。頁面只負責列表、排序、篩選與展開詳情，不引入 React 或其他前端框架。

Rationale:
- 目前 repo 沒有既有前端基礎，直接做 SPA 成本過高
- server-rendered HTML 已足夠解決「好讀、可分享、可快速開啟」這類需求

Alternatives considered:
- 直接開發完整 React / Next.js 前端
  - Rejected: 對目前產品成熟度來說太重
- 完全留在 LINE 文字回覆
  - Rejected: 無法有效呈現多筆候選房源與比較資訊

### 2. `/清單` 改成雙層顯示：LINE rich preview + 旅次詳情頁連結

`/清單` 第一層回覆以 LINE rich message 呈現當前旅次的重點候選，包含名稱、平台、價格、狀態與入口按鈕。第二層提供詳情頁連結，讓使用者進一步瀏覽完整清單。

Rationale:
- 使用者仍以 LINE 為主要操作入口，不應被迫先跳離聊天才看得到內容
- 先看預覽、再開頁面，比只丟一個 Notion URL 更容易理解

Alternatives considered:
- `/清單` 只回旅次頁 URL
  - Rejected: 缺乏即時可見的摘要感
- `/清單` 繼續只回 Notion 連結
  - Rejected: 仍然把主要顯示責任放在 Notion

### 3. 顯示層直接讀 Mongo canonical data，Notion 降級為 export surface

旅次頁與 LINE 預覽都使用 Mongo 中的住宿資料與旅次資料建模，不透過 Notion 反查畫面內容。若該旅次存在 Notion export，顯示層只把 Notion 視為額外跳轉選項。

Rationale:
- Mongo 才是穩定的 source of truth
- 這樣可以把 schema 演進壓在程式內，而不是壓在 Notion migration

Alternatives considered:
- 仍以 Notion 為主，Mongo 只當備份
  - Rejected: 會持續遇到欄位演進與舊表殘留問題

### 4. 旅次頁使用穩定 share token，而不是依賴 LIFF context

由 server 為每個旅次產生穩定的只讀 token 或 share slug，`/清單` 產出的頁面連結直接帶入這個識別。第一版不依賴 LIFF chat context，也不要求使用者登入。

Rationale:
- LIFF 不適合當作聊天室 scope 的唯一辨識來源
- 穩定分享連結更符合使用者從 LINE 反覆打開旅次頁的情境

Alternatives considered:
- 只用短效簽名 URL
  - Rejected: 連結過期會降低實用性
- 導入完整登入驗證
  - Rejected: 超出這個 change 的必要範圍

## Risks / Trade-offs

- [新增 HTML 顯示層會帶來模板維護成本] → 用只讀頁與極少量互動控制範圍
- [公開連結若處理不當可能暴露旅次資料] → 使用不含敏感 scope 資訊的 share token，避免直接暴露 `group_id` / `room_id`
- [LINE rich preview 版面有限] → 僅顯示前幾筆重點候選，其餘導向詳情頁
- [Notion 不再是主畫面，使用者可能不習慣] → 在旅次頁中保留「打開 Notion」入口作為過渡

## Migration Plan

1. 新增旅次顯示所需的 query model、share token 與頁面 route
2. 實作只讀旅次頁與 mobile-first 樣式
3. 更新 `/清單`，改用 rich preview 與詳情頁連結
4. 將 Notion link 改為顯示層中的次要入口，並更新 README / 操作說明

Rollback strategy:
- `/清單` 可回退成單純連結回覆
- 旅次頁 route 可停用，不影響 Mongo 與 Notion 既有資料

## Open Questions

- 第一版 rich preview 要顯示幾筆候選最剛好，3 筆、5 筆，還是依 LINE message 限制動態決定？
- 旅次頁是否需要「已淘汰 / 已決定」這類手動狀態欄位，還是先只顯示收錄結果？
- 是否要把既有 `add-lodging-decision-summary` 的摘要結果嵌進旅次頁，還是先只保留 API 整合點？
