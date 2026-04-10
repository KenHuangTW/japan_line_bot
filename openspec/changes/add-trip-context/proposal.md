## Why

目前系統用 LINE 聊天室作為主要資料範圍，同一群人跨多次旅行時，房源會被累積在同一個 scope 內，缺少「這次旅行」的明確上下文。若不先解決旅次切換與封存問題，後續的整理、同步與決策功能都會持續混在一起。

## What Changes

- 新增旅次管理流程，讓每個 LINE 聊天室可以建立、切換、查詢與封存目前旅次。
- 將房源收錄與重複判斷從聊天室範圍擴充為旅次範圍，讓同一聊天室的不同旅次可以各自保存相同房源。
- 將 `/清單`、`/整理`、`/全部重來` 改為以 active trip 為主要範圍，而不是只看聊天室。
- 補上 README 與測試，覆蓋旅次指令、沒有 active trip 時的行為，以及 trip-scoped 收錄與同步。

## Capabilities

### New Capabilities
- `trip-context`: 支援在 LINE 聊天室中建立、切換、查詢與封存目前旅次，並讓後續房源收錄與整理流程以旅次為主要工作上下文。

### Modified Capabilities
- None.

## Impact

- Affected code: `app/controllers/line_webhook_controller.py`, `app/models/*`, `app/controllers/repositories/*`, `app/notion_sync/*`, `app/map_enrichment/*`, `app/config.py`, `tests/*`, `README.md`
- Data/API: MongoDB 文件會新增旅次識別欄位；LINE 指令會新增旅次管理指令；Notion target mapping 會改成 trip-scoped
- Dependencies/systems: 不新增新的外部服務依賴，但後續功能會以這個 trip context 作為前置基礎
