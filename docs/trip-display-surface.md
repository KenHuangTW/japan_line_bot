# Trip Display Surface

這份文件描述 `add-trip-display-surface` change 完成後的操作行為，以及 `/摘要` 目前實際重用的 canonical payload。

## 定位

- MongoDB 是旅次顯示層的 source of truth。
- `/清單` 不再只回 Notion 連結，而是回傳 LINE 可讀 preview + 旅次詳情頁連結。
- Notion 是可選 export surface；沒有 Notion target 時，旅次顯示仍然成立。

## 使用入口

### LINE 指令

- `/清單`
  - 需要目前聊天室有 active trip。
  - 會回傳目前旅次的 LINE Flex carousel。
  - 每筆候選住宿會是一張獨立 card。
  - 若 enrichment 已產生 `line_hero_image_url`，card 會直接使用這個 Mongo 欄位顯示縮圖。
  - 會附上 `http(s)://.../trips/{display_token}` 連結。
  - 若該旅次有 Notion target，也會附上 Notion 匯出捷徑。

### Web route

- `GET /trips/{display_token}`
  - 使用穩定的 read-only token，不暴露 raw LINE scope ids。
  - 預設顯示全部候選住宿。
  - 支援 query 參數：
    - `platform`
    - `availability=all|available|sold_out|unknown`
    - `sort=captured_desc|captured_asc|price_asc|price_desc`

## 顯示資料來源

旅次頁與 LINE preview 都透過 `app.trip_display.MongoTripDisplayRepository` 從 Mongo 聚合：

1. `line_trips`
   - 取得 `display_token` 對應的 trip metadata
2. `captured_lodging_links`
   - 依 `trip_id` + source scope 讀取 canonical lodging records
3. `notion_targets`
   - 若存在 trip-scoped target，補上次要的 Notion 匯出連結

`LineTrip.display_token` 是穩定分享 token。舊 trip 文件若尚未有這個欄位，`MongoTripRepository` 會在讀取時 lazy backfill。

## Canonical payload

後續若要做 AI 摘要，不應再自己重新組 Mongo query；請直接重用 trip display surface。

建議整合點：

```python
surface = trip_display_repository.build_trip_display(trip, TripDisplayFilters())
payload = surface.to_summary_payload()
```

`payload` 結構包含：

- `trip`
  - `trip_id`
  - `title`
  - `status`
  - `display_token`
- `filters`
  - 目前使用的 platform / availability / sort
- `summary`
  - `total_lodgings`
  - `visible_lodgings`
  - `available_count`
  - `sold_out_count`
  - `unknown_count`
  - `notion_export_url`
- `lodgings[]`
  - `document_id`
  - `platform`
  - `property_name`
  - `display_name`
  - `city`
  - `hero_image_url`
  - `line_hero_image_url`
  - `target_url`
  - `formatted_address`
  - `price_amount`
  - `price_currency`
  - `availability`
  - `is_sold_out`
  - `amenities`
  - `maps_url`
  - `notion_page_url`
  - `captured_at`
  - `updated_at`

## Operator notes

- `/清單` 與 `/trips/{display_token}` 不依賴 Notion schema，Notion 壞掉也不應影響主要顯示流程。
- `/摘要` 現在已直接重用這份 payload；若要調整 AI 輸入欄位，請先改 `app.trip_display`，再看 `app/lodging_summary/`。
- `hero_image_url` 是原始抓到的主圖；`line_hero_image_url` 是已過 LINE 相容性篩選、可直接給 Flex hero image 用的欄位。
- 若使用者抱怨看不到 Notion 入口，先檢查該旅次是否已有 scoped target，而不是先看旅次頁本身。
- 若需要重新產生 Notion target，可使用 scoped `POST /jobs/notion-sync/setup` 或在該旅次執行 `/全部重來`。
- 若需要調整旅次頁排序/篩選規則，優先改 `app.trip_display`，不要在 LINE preview 與 HTML route 各自維護一份邏輯。
