## Context

現有專案已經有 `map_enrichment_job.py` 與 `notion_sync_job.py` 這種由外部排程呼叫的批次入口，因此定期 refresh 最自然的延伸方式，是新增一個 trip refresh job 來協調「列出 active trip -> 逐 trip 重跑 enrichment -> 逐 trip sync Notion」。這個 change 假設旅次 context 已經存在，並以 active trip 作為唯一刷新範圍。

第一版不追求最細的 pricing-only refresh，而是先用現有 enrichment / sync pipeline 完成一條可運行的定期更新流程。

## Goals / Non-Goals

**Goals:**
- 提供一個外部可呼叫的 trip refresh job
- 只刷新 active trip，跳過 archived trip
- 逐 trip 執行 enrichment 與 Notion sync
- 單一 trip 失敗時不影響其他 trip

**Non-Goals:**
- 不在服務內嵌常駐 scheduler
- 不做 pricing-only 專屬 refresh pipeline
- 不做跨 trip 的優先級排序或併發控制優化

## Decisions

### 1. Refresh 採 trip batch coordinator，而不是直接改現有單一 job 的全域行為

新增一個 coordinator job，先查出 active trips，再逐一呼叫現有 trip-scoped enrichment 與 sync 邏輯。`map_enrichment_job.py` 與 `notion_sync_job.py` 保持可單獨執行，trip refresh job 則作為更高一層的協調入口。

Rationale:
- 可以最大化重用現有 job 能力
- 避免把所有 refresh 邏輯塞進單一既有 job，降低回歸風險

Alternatives considered:
- 直接讓現有 enrichment job 自動遍歷所有 trip
  - Rejected: 會模糊原本 job 的單一職責

### 2. 第一版 refresh 全量重用現有 enrichment pipeline

每次 refresh 直接重跑該 trip 範圍的 enrichment，再接續 Notion sync。即使這代表不只價格會更新，仍優先換取較低的實作複雜度。

Rationale:
- 現有系統已經把 enrichment 與 sync 拆成成熟流程
- 先交付可工作的排程，比提早優化 pricing-only 更重要

Alternatives considered:
- 第一版只做價格 / availability refresh
  - Rejected: 目前沒有足夠獨立的 pricing pipeline 可以直接重用

### 3. 失敗隔離以 per-trip 為單位

coordinator 在處理單一 trip 失敗時，記錄該 trip 的錯誤並繼續執行剩餘 active trips。最後輸出整體摘要，包含成功與失敗 trip 數量。

Rationale:
- 批次排程最重要的是整體可用性，不應因單一 trip 壞掉而整批停擺

Alternatives considered:
- 任一 trip 失敗就中止整個排程
  - Rejected: 運維風險過高，且對其他旅次不公平

## Risks / Trade-offs

- [12 小時全量 refresh 可能增加 HTTP 壓力] → 第一版僅鎖定 active trips，並沿用既有 batch size / timeout / retry 控制
- [trip 數量成長後，批次時間可能變長] → coordinator 先保留摘要與錯誤紀錄，後續再評估併發與優先級
- [依賴旅次 context，若前置 change 未完成就無法落地] → 在文件與 tasks 中明確標示前置依賴

## Migration Plan

1. 新增 active trip 查詢與 refresh coordinator job
2. 串接 trip-scoped enrichment 與 Notion sync
3. 補上排程與失敗隔離測試
4. 更新 README，說明外部 12 小時排程方式

Rollback strategy:
- 停用新的 trip refresh job 即可，不影響手動 `/整理` 與 `/全部重來`

## Open Questions

- 第一版要不要限制每次 refresh 最多處理幾個 active trip？
- refresh summary 是否需要額外輸出到監控或通知管道？
