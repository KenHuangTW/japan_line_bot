## Context

目前 `app/controllers/line_webhook_controller.py` 會直接使用 `event.source` 建立 chat scope，並將這個 scope 套進旅次管理、`/清單`、`/整理`、`/全部重來`、住宿收錄、duplicate lookup 與自動 Notion sync 等流程。這種設計在正常群組內操作沒有問題，但無法滿足「在安靜聊天室 A 發指令與貼連結，實際控制正式群組 B」的需求。

現有架構已經把大多數 scope-sensitive 的指令集中在 `_handle_line_command()` 與 `_resolve_chat_scope()` / `_resolve_active_trip_scope()`，而 capture path 也集中在 `process_events()` 的單一路徑。因此這個 change 仍然不需要新增外部系統，但需要把「回覆來源」與「資料作用範圍」正式拆開：回覆要跟著原始事件留在 A，資料查詢與持久化則要導向 B。

## Goals / Non-Goals

**Goals:**
- 新增一組可選的 env 設定，定義控制聊天室 A 與被控制聊天室 B 的 `group_id`
- 當使用者在 A 發出 scope-sensitive 的 LINE 指令或貼住宿連結時，讓資料流程改以 B 作為 target scope
- 保持 LINE reply token 與 reply message 留在 A，但讓 active trip、duplicate lookup、capture 儲存與後續 sync 都以 B 為準
- 優先維持現有資料模型與 repository query，不新增新的外部依賴，將變更限制在 config 與 webhook/controller 層
- 補上 README 與 webhook regression tests，讓操作方式和限制明確可見

**Non-Goals:**
- 不支援多組 A/B 映射或動態管理映射
- 不支援 `room_id` / `user_id` 的跨聊天室控制
- 不把 `/help`、`/ping` 這類不依賴資料 scope 的回覆改成遠端執行
- 不處理歷史 trip、Notion target 或既有資料的搬移

## Decisions

### 1. 使用兩個明確 env 欄位表達單一控制映射

在 `Settings` 中新增兩個可選欄位，例如 `LINE_COMMAND_CONTROL_SOURCE_GROUP_ID` 與 `LINE_COMMAND_CONTROL_TARGET_GROUP_ID`。只有兩者都存在且非空時，功能才啟用。

Rationale:
- 使用者需求明確是單一 A/B 聊天室對應，不需要更抽象的設定格式
- 獨立欄位比 JSON / CSV map 更容易在 `.env`、README 與部署環境中維護

Alternatives considered:
- 使用 JSON dictionary 表示多組映射
  - Rejected: 第一版過度設計，且會增加 config 驗證與文件成本

### 2. 將「資料 target scope」與「回覆來源」分離，不改寫原始 webhook event

新增集中式 helper，讓 command path 與 capture path 都能取得「資料 target scope」。當事件來源是 group 且 `groupId` 命中控制聊天室 A 時，helper 會回傳代表被控制聊天室 B 的衍生 source；未命中時則回傳原始聊天室 source。原始 `event.source` 與 `replyToken` 保持不變，回覆仍然送回 A。

Rationale:
- 控制聊天室 A 應該像操作台，負責接收互動與回覆；被控制聊天室 B 才是資料真實歸屬
- 不改寫整個 webhook event，可以降低對 reply、signature 驗證與非 scope 資料的影響

Alternatives considered:
- 直接把 `event.source.groupId` 取代成 B 的 group id
  - Rejected: 雖然資料會對，但會讓回覆來源與原始事件語意混在一起，debug 成本更高

### 3. 讓 scope-sensitive 指令與住宿收錄都吃到 override，但 `/help`、`/ping` 保持本地

override 會影響會查詢或修改旅次 / trip-scoped 資料的指令：`/建立旅次`、`/切換旅次`、`/目前旅次`、`/封存旅次`、`/清單`、`/整理`、`/全部重來`，以及一般住宿連結貼文的 active trip 解析、duplicate lookup、capture 儲存與自動 sync。`/help` 與 `/ping` 仍保留原本的本地回覆行為，不需要知道 target scope。

Rationale:
- 使用者現在要的是「在 A 操作，但紀錄給 B」，所以住宿收錄與後續同步也必須跟著導向 B
- `/help`、`/ping` 不依賴資料 scope，硬套 override 只會增加理解成本

Alternatives considered:
- 只代理 command，不代理住宿收錄
  - Rejected: 這會讓私下操作與資料實際歸屬分離，仍然無法在 A 完整維運 B 的旅次資料

### 4. Capture path 直接以 target scope 寫入 B，回覆仍留在 A

當控制聊天室 A 貼出住宿連結時，active trip 解析、duplicate lookup、`CapturedLodgingLink` 上的 `source_type/group_id/room_id/user_id`、自動 map enrichment 與 Notion sync 都改用 target scope B。LINE reply 還是用原始事件的 `replyToken`，因此訊息回在 A。

Rationale:
- 使用者要的是「在 A 貼上，在 A 回覆，但紀錄給 B」，資料欄位與後續 job 都必須一致地視為 B 的資料
- 若只在 append 時改寫 `group_id`，但 duplicate lookup 或 auto sync 仍用 A，就會產生前後不一致

Alternatives considered:
- 只在最終儲存時把 `group_id` 改成 B，前面的 active trip / duplicate lookup 仍用 A
  - Rejected: 會導致 duplicate 判斷、旅次要求與後續 sync scope 全部不一致

### 5. 不完整或未命中的設定一律安全 fallback

若 env 只填了一邊、來源不是 `group`、或事件來自非控制聊天室，系統一律回到原本的 source-based 行為，不報錯也不阻斷 webhook。

Rationale:
- 這是可選功能，不應讓機器人在未配置完全時變成不可用
- fallback 行為與現況一致，最容易部署與回滾

Alternatives considered:
- 啟動時只要設定不完整就直接拒絕啟動
  - Rejected: 對可選功能而言過於嚴格，會提高部署風險

## Risks / Trade-offs

- [控制聊天室與實際收錄聊天室不同，操作者需要記住資料最終屬於 B] → 在 README 與回覆文案中明確說明 A 是控制入口、B 是資料 scope
- [單一 A/B 映射無法覆蓋未來多群組維運情境] → 先用最小配置滿足當前需求，未來若真的需要再擴充成多映射格式
- [A 貼連結會直接寫進 B，若設定錯誤會把資料收進錯的旅次] → 保持 feature 顯式 opt-in，並用 regression tests 保證 fallback 與 scope 一致性

## Migration Plan

1. 在 `Settings` 新增 command-scope override env 欄位與 helper
2. 將 scope-sensitive 指令與 capture path 的資料 scope 解析改為經過 target-scope resolution
3. 補上 webhook regression tests，驗證 A 發指令與貼連結都會命中 B，但 reply 仍留在 A
4. 更新 README 與 `.env.example`（若 repo 補上範例檔）說明設定方式與限制

Rollback strategy:
- 移除或清空新增的 env 設定即可停用功能
- 若需完全回退，移除 target-scope resolution helper，恢復直接使用原始 `event.source`

## Open Questions

- 未來是否需要支援多組控制聊天室映射，或 `room_id -> group_id` 的跨類型代理？第一版先不處理。
