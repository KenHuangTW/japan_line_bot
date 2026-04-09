## Context

目前住宿連結流程以平台專屬判斷為核心：`supported_domains` 先決定 extractor 會接受哪些網域，`LodgingLinkService` 再依 `booking` / `agoda` 分別做住宿頁與分享連結判斷，`build_lodging_lookup_keys` 負責 canonical URL 去重，最後 enrichment 與 Notion sync 依既有欄位把資料補齊並同步出去。

Airbnb 缺口不只是一個 domain 白名單問題，還同時影響平台判斷、非住宿頁過濾、canonical URL 去重、enrichment 的 fallback 路徑，以及 Notion `platform` select option。這是一個跨 `config`、`lodging_links`、`map_enrichment`、`notion_sync` 與 webhook 測試的橫向變更，適合先用設計文件把範圍與取捨寫清楚。

## Goals / Non-Goals

**Goals:**
- 讓 direct Airbnb 房源頁可以進入既有的 capture -> dedupe -> enrichment -> Notion sync 流程
- 保持 Booking.com / Agoda 現有行為不變，延續現有 provider-based 結構
- 對 Airbnb 採用 best-effort enrichment，優先用穩定的 structured data 與通用 HTML fallback
- 讓 Notion target schema 能直接承接 `airbnb` 平台值

**Non-Goals:**
- 不處理 Airbnb Experiences、搜尋結果、收藏清單、房東 profile 等非單一房源頁面
- 不引入瀏覽器自動化、登入流程、captcha / anti-bot 繞過機制
- 不在第一階段保證支援 app-only deep link 或未確認格式的短網址；先以公開 web listing URL 為主

## Decisions

### 1. 新增 Airbnb provider 模組，而不是把網址判斷塞進通用 regex

建立 `app/lodging_links/airbnb.py`，和 `booking.py` / `agoda.py` 一樣提供 hostname、lodging URL、non-lodging URL 判斷與 `classify_airbnb_url`。`LodgingLinkService`、`map_enrichment.service._get_resolution_plan`、共用匯出都走同一層 provider dispatch。

Rationale:
- 目前程式就是 provider-specific classifier 架構，沿用可以把 Airbnb 行為收斂在單一模組
- Airbnb 需要明確排除非房源頁，單靠 extractor 的 domain 白名單無法做到

Alternatives considered:
- 只擴充 `supported_domains`
  - Rejected: 會把大量非房源 Airbnb URL 放進後續流程
- 寫單一 generic classifier
  - Rejected: 不利於日後調整各平台規則，也會讓既有模組邊界變模糊

### 2. 第一階段只承諾公開 web listing URL，短網址延後

Requirement 層只承諾支援可直接對應到單一房源頁的 Airbnb public listing URL，例如 canonical path 以 `/rooms/<listing-id>` 為核心的頁面。若未來拿到穩定、可測試的 Airbnb 短網址樣本，再額外擴充 resolver 規則。

Rationale:
- 現有 repo 沒有 Airbnb 分享網址樣本，也沒有可靠的短網址平台對應規則
- 先把最常見、最可驗證的 listing URL 做好，可以避免 spec 先承諾不穩定格式

Alternatives considered:
- 同步支援所有 Airbnb 分享 / deep link
  - Rejected: 目前缺少樣本與驗證依據，容易讓 spec 超過可落地範圍

### 3. Enrichment 走通用 parser 優先，Airbnb 只補 provider-specific fallback

Airbnb enrichment 會優先重用 `parse_lodging_map()` 的 JSON-LD / HTML 通用解析能力，必要時只新增與 Airbnb path 或 HTML 結構相關的輕量 fallback，例如從 `/rooms/<id>` 之外的 path slug 補 property name，或補強公開頁常見欄位的抽取邏輯。`LodgingMapEnrichmentService` 對 Airbnb 失敗時仍要回到 partial result 友善的模式，不因單一欄位缺失而丟棄整筆房源。

Rationale:
- 目前 parser 已能從 schema.org / JSON-LD 解析名稱、地址、座標、房型與價格，Airbnb 若也公開這些資訊，就不需要重寫一套 parser
- 用 provider-specific fallback 補洞，比直接建立大量 brittle selector 更耐 HTML 變動

Alternatives considered:
- 建立完整 Airbnb 專屬 parser
  - Rejected: 維護成本高，且會和現有 generic parser 重複
- 用 headless browser 抓動態資料
  - Rejected: 明顯超出目前服務複雜度與部署成本

### 4. Airbnb 視為一級平台值，不用 `unknown` 代替

`platform` 欄位、Notion `PLATFORM_OPTIONS`、README 與測試資料都直接加入 `airbnb`。這讓 duplicate triage、Notion filter、後續報表與平台特化邏輯都能正確辨識 Airbnb。

Rationale:
- 既有系統明顯依賴平台值做流程分流與展示
- 若把 Airbnb 存成 `unknown`，會讓 Notion 篩選、未來 provider-specific enrich 以及除錯都失去上下文

Alternatives considered:
- 暫時存成 `unknown`
  - Rejected: 只能暫時避免 schema 變更，卻會讓 downstream 行為不準確

## Risks / Trade-offs

- [Airbnb 公開頁 HTML 與 metadata 可能依 locale 或登入狀態變動] → 優先依賴 JSON-LD 與通用欄位，並讓 partial enrichment 成為合法結果
- [第一階段不支援未確認的短網址格式，可能漏掉部分 app 分享連結] → 上線後收集真實樣本，再以增量 change 擴充
- [新增 platform option 會影響既有 Notion target schema] → 讓 sync service 在 ensure/update schema 時自動補上 `airbnb` option，避免手動 migration
- [Airbnb URL canonicalization 若規則太寬，可能把非同一 listing 視為重複] → 僅對明確 listing path 做 canonicalization，並保留 provider-specific 測試案例

## Migration Plan

1. 擴充 `supported_domains` 與 Airbnb classifier，讓 webhook 可以先收 direct listing URL
2. 更新 canonicalization / lookup pattern 與平台值，確認同房源不會被重複收錄
3. 補上 Airbnb enrichment 與測試，確保 partial metadata 不會阻塞 capture 流程
4. 更新 Notion schema option 與 sync 測試，確認既有 data source 可平滑接受 `airbnb`
5. 更新 README 與操作說明後部署；若需要 rollback，移除 Airbnb domain 與 classifier dispatch 即可回到原本支援範圍

## Open Questions

- 真實使用者貼出的 Airbnb 連結中，是否有高比例來自 app share short link？如果有，需要先收集至少一批樣本再決定是否擴 scope
- 目前是否接受 Airbnb enrichment 只有名稱 / 地址、沒有價格或精準座標的結果？本設計假設可以接受，因為這比完全丟棄房源更有價值
