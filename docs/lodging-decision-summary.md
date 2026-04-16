# Lodging Decision Summary

這份文件描述 `add-lodging-decision-summary` change 完成後的操作行為，以及 `/摘要` 指令的設定與降級規則。

## 目的

- `/摘要` 只處理目前 active trip。
- 摘要輸入只來自 Mongo canonical lodging payload，不讀原始 LINE 對話，也不讀 Notion rich text。
- Gemini 必須回傳結構化 JSON；程式端會先驗證 schema，再轉成 LINE 文字回覆。

## 啟用方式

至少需要：

- `GEMINI_API_KEY`

可選設定：

- `GEMINI_MODEL`
  - 預設 `gemini-2.5-flash`
- `GEMINI_REQUEST_TIMEOUT`
  - 預設 `15.0`

未設定 `GEMINI_API_KEY` 時，`/摘要` 會直接回覆：

```text
AI 摘要尚未設定完成。
```

## LINE 使用方式

- `/摘要`
  - 需要目前聊天室已有 active trip。
  - 若目前旅次有住宿資料，會回覆：
    - 優先候選
    - 優點
    - 缺點
    - 待補資訊
    - 討論重點

## 資料來源

`/摘要` 不會自己重查 Mongo schema，而是直接重用 `app.trip_display` 的 canonical payload：

```python
surface = trip_display_repository.build_trip_display(trip, TripDisplayFilters())
payload = surface.to_summary_payload()
```

目前 payload 會提供給 AI 的重點欄位包含：

- `trip.trip_id`
- `trip.title`
- `summary.total_lodgings`
- `summary.available_count`
- `summary.sold_out_count`
- `lodgings[].document_id`
- `lodgings[].platform`
- `lodgings[].property_name`
- `lodgings[].display_name`
- `lodgings[].city`
- `lodgings[].formatted_address`
- `lodgings[].price_amount`
- `lodgings[].price_currency`
- `lodgings[].availability`
- `lodgings[].is_sold_out`
- `lodgings[].amenities`
- `lodgings[].maps_url`
- `lodgings[].captured_at`
- `lodgings[].updated_at`

## 失敗行為

- 沒有 active trip：

```text
目前沒有啟用中的旅次，請先用 /建立旅次 <名稱> 建立，或用 /切換旅次 <名稱> 切換。
```

- active trip 內沒有住宿資料：

```text
目前旅次還沒有住宿資料可摘要，請先貼住宿連結。
```

- Gemini timeout、HTTP 失敗、回傳非 JSON 或 schema 驗證失敗：

```text
目前無法產生住宿摘要，請稍後再試。
```

失敗時只影響這次回覆，不會改動 trip 或 lodging 資料。
