## Why

即使房源已經被收錄，價格與可售狀態仍會隨時間變動；若沒有定期 refresh，討論時看到的資料很快就會過期。旅次一旦成為主要工作上下文，就需要一個可以針對 active trip 定期重整資料的批次流程。

## What Changes

- 新增 active trip 導向的 refresh job，由外部 scheduler 定期觸發。
- 讓 refresh job 列出所有 active trip，逐一重跑該旅次範圍內的 enrichment 與 Notion sync。
- 在單一旅次失敗時保留批次繼續處理其他旅次的能力。
- 補上 README 與測試，說明建議的 12 小時排程方式與失敗隔離行為。

## Capabilities

### New Capabilities
- `scheduled-trip-refresh`: 支援定期刷新 active trip 中仍在考慮的房源資料，優先更新價格與可售狀態，並將結果同步到 Notion。

### Modified Capabilities
- None.

## Impact

- Affected code: `app/map_enrichment_job.py`, `app/notion_sync_job.py`, `app/map_enrichment/*`, `app/notion_sync/*`, `app/config.py`, `tests/*`, `README.md`
- Data/API: 新增 trip refresh job 入口與執行摘要
- Dependencies/systems: 依賴外部 cron / workflow scheduler；此 change 依賴旅次 context 已存在，才能列舉 active trip
