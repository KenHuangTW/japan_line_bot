## Context

目前 webhook、去重、enrichment 與 Notion sync 都建立在 `source_scope` 之上，也就是 `group_id` / `room_id` / `user_id`。這個設計對單次旅行夠用，但不適合同一個聊天室反覆規劃不同旅次，因為使用者需要的是像 `use db` 一樣先切換環境，再把後續房源都歸進該環境。

專案已經有指令式互動與 scoped Notion target 的基礎，因此旅次功能不需要推翻現有架構，而是要在 source-scope 之上新增一層 trip context，讓 capture、sync、list 都改從 active trip 出發。

## Goals / Non-Goals

**Goals:**
- 讓每個 LINE 聊天室可以建立、切換、查詢與封存目前旅次
- 讓房源收錄、去重、`/清單`、`/整理`、`/全部重來` 改為以 active trip 為範圍
- 讓同一聊天室中的相同房源可以在不同旅次各自保留

**Non-Goals:**
- 不處理 AI 摘要與 refresh 排程
- 不做歷史資料自動搬遷到新旅次
- 不建立未分類或預設旅次當作保底收件匣

## Decisions

### 1. 新增獨立 trip collection，而不是只在房源文件上加字串標籤

建立 trip model / repository，記錄 `trip_id`、`source_scope`、`title`、`status`、`created_at`、`archived_at`，並保存每個聊天室目前的 active trip。房源文件則只攜帶 `trip_id` 與 `trip_title` 快照。

Rationale:
- active trip 需要獨立生命週期，不只是房源上的分類欄位
- trip collection 比單純字串標籤更容易做切換、封存與列出旅次

Alternatives considered:
- 只在房源文件新增 `trip_name`
  - Rejected: 無法可靠表達 active trip 與封存狀態

### 2. 沒有 active trip 時，支援房源一律拒收

若訊息中包含支援的住宿連結，但該聊天室沒有 active trip，系統直接回覆使用者先建立或切換旅次，不自動寫入任何未分類資料。

Rationale:
- 使用者已明確偏好「先選旅次再貼 URL」
- 自動收進未分類旅次會讓資料再次混雜

Alternatives considered:
- 自動建立 `未分類旅次`
  - Rejected: 長期會變成新的雜物堆

### 3. 去重與 Notion target 都改以 `trip_id` 為主範圍

duplicate lookup、Notion target resolution、`/清單`、`/整理`、`/全部重來` 都先解析 active trip，再以 `trip_id` 做 query。相同聊天範圍內，同一 URL 只在同一 trip 被視為重複。

Rationale:
- 若只把 capture 改成 trip-scoped，其他流程仍會用舊 scope，資料邏輯會不一致
- 既有 scoped Notion target 模式適合延伸成 trip-scoped

Alternatives considered:
- Notion 維持聊天室共用一個 data source
  - Rejected: 使用者還是得手動 filter 才能看到當前旅次

## Risks / Trade-offs

- [初次使用多一步旅次建立流程] → 用清楚的回覆訊息與 `/目前旅次` 指令降低摩擦
- [每個 trip 各自建立資料表，Notion target 會變多] → 用旅次封存與一致命名規則控制可管理性
- [新舊 source-scoped 資料共存一段時間] → 先把 trip 視為新流程，不強迫搬移舊資料

## Migration Plan

1. 新增 trip model、repository 與 Mongo collection
2. 新增旅次管理指令與 active trip 解析流程
3. 擴充 capture / duplicate lookup / Notion target query，全面改為 trip-scoped
4. 更新 README 與測試

Rollback strategy:
- 停用旅次指令並回復 source-scoped query 即可
- 已存在文件上的 `trip_id` 欄位可保留，不影響舊版讀取

## Open Questions

- `/切換旅次` 第一版要用旅次名稱比對，還是要先列出最近旅次再切換？
- 是否需要加 `/旅次列表` 指令作為輔助操作？
