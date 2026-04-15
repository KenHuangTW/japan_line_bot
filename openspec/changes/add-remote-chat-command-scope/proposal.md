## Why

目前所有 LINE 指令與住宿連結收錄都直接以事件來源聊天室作為 scope，導致若使用者想在一個安靜的私人聊天室操作另一個正式群組的旅次資料，就只能直接去正式群組下指令和貼連結。這會打擾其他群組成員，也讓旅次維運與房源整理缺少私下操作入口。

## What Changes

- 新增可選的 `.env` 聊天室控制映射，定義控制聊天室 A 與被控制聊天室 B 的 LINE `group_id`。
- 當 LINE 指令或住宿連結從控制聊天室 A 發出時，將資料作用範圍改為被控制聊天室 B，而不是 A 自己。
- 保留 LINE 回覆在控制聊天室 A 發生，但旅次查詢、duplicate lookup、capture 儲存、Notion sync 與後續資料處理都改以 B 為準。
- 將旅次管理、trip-scoped 指令與住宿收錄的 scope 解析抽出成明確的 target-scope resolution，避免在各功能內零散替換 `group_id`。
- 補上 README 與測試，覆蓋 env 設定、scope 轉向、控制聊天室貼連結會寫到 B、回覆仍在 A，以及未命中映射時的 fallback。

## Capabilities

### New Capabilities
- `remote-chat-command-scope`: 支援在指定控制聊天室中發出 LINE 指令與貼住宿連結，並將資料作用範圍導向另一個被控制聊天室，同時保留回覆在控制聊天室。

### Modified Capabilities
- None.

## Impact

- Affected code: `app/config.py`, `app/controllers/line_webhook_controller.py`, `app/schemas/line_webhook.py`, `tests/test_webhook.py`, `README.md`
- Data/API: 不新增外部 API；LINE 指令與住宿收錄流程的 target scope 解析會新增 env-based override
- Dependencies/systems: 需在 `.env` 增加控制聊天室與被控制聊天室的 group id 設定；不新增外部服務依賴
