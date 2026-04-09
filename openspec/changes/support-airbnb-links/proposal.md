## Why

目前系統只會收錄 Booking.com 與 Agoda 的住宿連結，群組中貼出的 Airbnb 房源會在擷取階段直接被忽略，導致後續的去重、補資料與 Notion 同步都無法涵蓋這類房源。旅遊規劃常同時比較飯店與民宿，Airbnb 缺席會讓收集流程中斷，增加手動整理成本。

## What Changes

- 新增 Airbnb 網址辨識能力，讓 webhook 可以從訊息中擷取 Airbnb 住宿頁連結，並忽略非住宿頁的 Airbnb 網址。
- 將 `airbnb` 納入既有的住宿平台流程，讓 capture、duplicate lookup、MongoDB 文件與 Notion 同步都能保留正確的平台資訊。
- 為 Airbnb 新增住宿頁 enrichment 流程，優先重用現有的 structured data / HTML 解析能力，並在公開頁面可取得資料時補上名稱、地址、座標、房型細節、設施與價格。
- 補上 README 與測試，覆蓋 extractor、lodging link service、webhook、map enrichment、Notion sync 的 Airbnb 情境。

## Capabilities

### New Capabilities
- `airbnb-lodging-links`: 支援擷取、判斷、儲存、補齊與同步 Airbnb 住宿房源連結。

### Modified Capabilities
- None.

## Impact

- Affected code: `app/config.py`, `app/link_extractor.py`, `app/lodging_links/*`, `app/map_enrichment/*`, `app/notion_sync/service.py`, `app/controllers/line_webhook_controller.py`, `tests/*`, `README.md`
- Data/API: `supported_domains` 預設值會新增 Airbnb；MongoDB / Notion 中的 `platform` 欄位會開始出現 `airbnb`
- Dependencies/systems: 沿用既有 HTTP fetch 與 URL resolve 能力，不新增新的外部服務依賴
