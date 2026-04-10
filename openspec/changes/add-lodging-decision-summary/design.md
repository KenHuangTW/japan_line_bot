## Context

決策摘要的真正需求不是把聊天內容重新寫成文章，而是從已經收錄好的房源資料中萃取出討論所需的重點。這個 change 假設系統已經具備 active trip 概念，因此 summary command 只需要抓取目前旅次的房源資料，產生候選排序、優缺點與待補資訊即可。

目前專案還沒有 LLM 整合層，因此這個 change 需要新增外部 AI provider client、輸入/輸出 schema，以及在 controller 端安全處理 AI 失敗的邏輯。

## Goals / Non-Goals

**Goals:**
- 提供可手動觸發的旅次摘要指令
- 僅以結構化房源資料作為 AI 輸入
- 要求模型回傳結構化 JSON，並在程式端驗證後再轉成 LINE 訊息
- 摘要失敗時不影響旅次或房源資料

**Non-Goals:**
- 不在每次收錄後自動重跑摘要
- 不把摘要寫回 Notion
- 不把原始聊天紀錄直接送進模型
- 不做投票、加權評分或最終自動決策

## Decisions

### 1. 摘要只允許 command-triggered，不走自動背景生成

新增 `/摘要` 指令，由使用者在需要討論時手動觸發。系統只為 active trip 生成一次即時摘要，不持久化到資料庫。

Rationale:
- 符合實際使用時機，也可控制 API 成本
- 避免每次貼新連結就重跑摘要造成噪音

Alternatives considered:
- 每次 capture 後自動摘要
  - Rejected: 成本高且輸出變動頻繁

### 2. AI 輸入以 normalized lodging payload 為唯一來源

從目前旅次的房源文件整理最小必要欄位，例如 `property_name`、`platform`、`city`、`price_amount`、`price_currency`、`is_sold_out`、`amenities`、`maps_url`、`last_updated_at`。不直接傳送原始訊息或 Notion rich text。

Rationale:
- 降低隱私暴露與無關內容
- 讓 prompt 更穩定，摘要品質更可控

Alternatives considered:
- 直接送聊天紀錄或 Notion 頁面內容
  - Rejected: 噪音高，也會把資料來源耦合到 UI 表現

### 3. 使用 structured output schema 驗證模型回傳

Gemini response 必須符合程式定義的 summary schema，例如：
- `top_candidates`
- `pros`
- `cons`
- `missing_information`
- `discussion_points`

controller 在 schema 驗證成功後才渲染成 LINE 回覆；若驗證失敗，視為摘要失敗。

Rationale:
- 結構化輸出比自由文本更容易測試與維護
- 可以避免回傳格式飄移破壞 LINE 呈現

Alternatives considered:
- 直接渲染模型自由文本
  - Rejected: 難測試也難保證穩定格式

## Risks / Trade-offs

- [摘要品質依賴資料完整度] → 在輸出中保留 `missing_information` 區段，明確標示缺漏
- [外部 AI 依賴會增加 timeout 與錯誤情境] → 設定明確 timeout，並在 controller 端安全降級
- [摘要內容可能過長，不適合 LINE 單次回覆] → 將 schema 與渲染格式限制為精簡段落與候選數量

## Migration Plan

1. 新增 Gemini 設定與 client abstraction
2. 定義 summary request/response schema 與 service
3. 在 webhook controller 中加入摘要指令與錯誤處理
4. 補上測試與 README

Rollback strategy:
- 停用摘要指令與 AI service 即可，不影響其他旅次或房源流程

## Open Questions

- 第一版 `/摘要` 是否需要限制只列前 3 或前 5 個候選？
- 是否需要為摘要結果增加固定的「建議討論順序」欄位？
