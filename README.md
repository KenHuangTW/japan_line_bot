# Nihon LINE Bot

這是一個用 FastAPI 實作的 LINE bot webhook MVP，先專注把「群組丟出 Booking / Agoda 住宿連結」這件事收進系統。

目前功能：

- 驗證 LINE webhook 簽章
- 接收群組或私聊的文字訊息
- 擷取 `booking.com` / `agoda.com` 連結
- 把住宿連結寫進 MongoDB
- 以 background job 解析住宿頁的地圖資訊
- 成功擷取後回覆一則確認訊息

## 專案結構

```text
app/
  config.py
  main.py
  line_client.py
  line_security.py
  line_service.py
  link_extractor.py
  collector.py
  models/
Dockerfile
docker-compose.yml
mongo.ps1
mongo.sh
start.ps1
start.sh
test.ps1
test.sh
tests/
```

## 使用 conda 建環境

```bash
conda env create -f environment.yml
conda activate nihon-line-bot
```

如果你想直接用現有 Python，也可以：

```bash
python3 -m pip install -e .[dev]
```

Windows PowerShell 也可以直接安裝：

```powershell
python -m pip install -e '.[dev]'
```

## 設定環境變數

先複製一份設定檔：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

你至少要填這兩個值：

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`

預設資料儲存設定如下：

- `MONGO_URI=mongodb://127.0.0.1:27017`
- `MONGO_DATABASE=nihon_line_bot`
- `MONGO_COLLECTION=captured_lodging_links`

如果你要把住宿資料同步到 Notion，另外要準備：

- `NOTION_API_TOKEN`
- `NOTION_PARENT_PAGE_ID`，用來建立第一個資料庫
- `NOTION_DATA_SOURCE_ID`，若已建立好資料庫可直接填；否則可先呼叫 setup API 取得

Notion 相關預設值：

- `NOTION_DATABASE_TITLE=Nihon LINE Bot Lodgings`
- `NOTION_API_VERSION=2026-03-11`
- `NOTION_REQUEST_TIMEOUT=10.0`
- `NOTION_SYNC_BATCH_SIZE=20`

## 啟動 MongoDB

本機用 Docker 跑 MongoDB：

```bash
./mongo.sh
```

Windows PowerShell：

```powershell
.\mongo.ps1
```

你也可以看 log 或停止服務：

```bash
./mongo.sh logs
./mongo.sh down
```

Windows PowerShell：

```powershell
.\mongo.ps1 logs
.\mongo.ps1 down
```

## 啟動服務

```bash
./start.sh
```

Windows PowerShell：

```powershell
.\start.ps1
```

健康檢查：

```bash
curl http://127.0.0.1:8000/healthz
```

執行測試：

```bash
./test.sh
```

Windows PowerShell：

```powershell
.\test.ps1
```

如果你已經把本機服務跑起來，想直接做一筆 webhook smoke test：

```bash
./test.sh smoke
```

Windows PowerShell：

```powershell
.\test.ps1 smoke
```

你也可以用環境變數改 host / port / conda env：

```bash
HOST=0.0.0.0 PORT=8001 CONDA_ENV_NAME=nihon-line-bot ./start.sh
```

Windows PowerShell：

```powershell
$env:HOST = "0.0.0.0"
$env:PORT = "8001"
$env:CONDA_ENV_NAME = "nihon-line-bot"
.\start.ps1
```

如果 PowerShell execution policy 擋住本機腳本，可以改用：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

## 執行住宿 enrichment job

把已經收進 MongoDB 的住宿連結補上名稱、地址、結構化地理欄位、房型細節、設備、頁面價格，以及 Google Maps 精準定位 / 搜尋備援連結：

```bash
python -m app.map_enrichment_job
```

這支 command 適合掛進 cron，定期掃描 `map_status = pending` 的文件；同一次執行會一併更新地理、細節與價格欄位。

可調整的環境變數：

- `MAP_ENRICHMENT_BATCH_SIZE=20`
- `MAP_ENRICHMENT_REQUEST_TIMEOUT=10.0`
- `MAP_ENRICHMENT_MAX_RETRY_COUNT=3`

## 執行 Notion sync job

把 MongoDB 中的住宿資料同步到 Notion data source：

```bash
python -m app.notion_sync_job
```

這支 command 會同步 `notion_sync_status = pending`、曾經同步失敗、或在前次成功同步後又被 enrichment 更新過的文件。

可調整的環境變數：

- `NOTION_SYNC_BATCH_SIZE=20`
- `NOTION_REQUEST_TIMEOUT=10.0`
- `NOTION_API_VERSION=2026-03-11`

## Swagger 觸發住宿 enrichment

如果你暫時不想設定 cron，可以直接開 Swagger 呼叫：

- `GET /jobs/lodging-enrichment/documents`
- `POST /jobs/lodging-enrichment/run`
- `POST /jobs/lodging-enrichment/documents/retry-all`
- `POST /jobs/lodging-enrichment/documents/{document_id}/retry`

舊的 `/jobs/map-enrichment/*` 路徑仍可使用，但 Swagger 會以新的 `/jobs/lodging-enrichment/*` 為主。

這兩支 API 的 200 response 會統一包成：

```json
{
  "is_success": true,
  "message": "string",
  "data": {}
}
```

建議驗證順序：

1. 先用 `GET /jobs/lodging-enrichment/documents?status=pending&limit=20` 看目前待解析資料
2. 再呼叫 `POST /jobs/lodging-enrichment/run`，可在 body 傳 `{"limit": 5}`
3. 最後再用 `GET /jobs/lodging-enrichment/documents?status=resolved&limit=20` 或 `status=partial` 看是否出現 `property_name`、`country_code`、`city`、`amenities`、`price_amount`、`google_maps_url`
4. 若想手動重跑所有文件，不看目前狀態，可呼叫 `POST /jobs/lodging-enrichment/documents/retry-all`
5. 若只想重跑單筆文件，可直接呼叫 `POST /jobs/lodging-enrichment/documents/{document_id}/retry`

`map_status = resolved` 代表已拿到精準座標；`map_status = partial` 代表目前只有住宿名稱或地址，尚未能精準定位。

如果資料解析失敗，可以用 `GET /jobs/lodging-enrichment/documents?status=failed&limit=20` 檢查 `map_error`

## Swagger 觸發 Notion sync

若你要先在 Notion 建立資料庫，可呼叫：

- `POST /jobs/notion-sync/setup`

request body 可選填：

```json
{
  "title": "Trip Lodgings"
}
```

setup 成功後，response 會回傳 `database_id` 與 `data_source_id`。建議把它們填回 `.env` 的 `NOTION_DATABASE_ID` / `NOTION_DATA_SOURCE_ID`，之後重啟服務即可持續使用同一個資料庫。

同步與檢查 API：

- `POST /jobs/notion-sync/run`
- `GET /jobs/notion-sync/documents`
- `POST /jobs/notion-sync/documents/{document_id}/retry`

`POST /jobs/notion-sync/run` 可選擇在 body 傳：

```json
{
  "limit": 20,
  "force": false
}
```

- `force = false` 只會同步 pending / failed / 已變更文件
- `force = true` 會忽略同步狀態，直接重跑所有文件

Notion data source 預設會建立這些欄位：

- `名稱`
- `平台`
- `房源URL`
- `Google 地圖 URL`
- `設施`
- `最後更新時間`
- `ID`

`最後更新時間` 會取住宿資料最後一次被系統更新的時間，優先反映地圖 / 細節 / 價格 enrichment，否則退回首次擷取時間。
如果你已經有舊版欄位的 data source，重新呼叫 `POST /jobs/notion-sync/setup` 也會把現有 schema 收斂成這 7 個欄位。

## 用 Docker Compose 跑整套服務

如果你想一起啟動 server + MongoDB：

```bash
docker compose up --build
```

服務會對外開：

- `http://127.0.0.1:8000`
- `mongodb://127.0.0.1:27017`

## LINE Developers Console 需要設定的地方

1. 建立一個 Messaging API channel
2. 開啟 `Allow bot to join group chats`
3. 把 webhook URL 指向你的公開 HTTPS 位址，例如：

```text
https://<your-domain>/webhooks/line
```

4. 啟用 webhook
5. 把 bot 邀進你們的 LINE 群組

本機開發如果沒有公開網址，可以先用 tunnel 工具，例如 Cloudflare Tunnel 或 ngrok。

## LINE 指令

- `/ping`：回覆 `pong`
- `/整理`：執行 Notion sync，只整理發出指令的那個聊天室中，pending / 尚未同步完成的資料
- `/全部重來`：忽略既有同步狀態，只把發出指令的那個聊天室中的資料強制重新同步到 Notion

## 目前資料格式

每擷取到一筆住宿連結，就會寫入 MongoDB `captured_lodging_links` collection，欄位包含：

- 平台
- 原始連結
- hostname
- resolved_url / resolved_hostname
- property_name / formatted_address
- street_address / district / city / region / postal_code / country_name / country_code
- latitude / longitude
- property_type / room_count / bedroom_count / bathroom_count / amenities
- price_amount / price_currency
- source_price_amount / source_price_currency / price_exchange_rate / price_exchange_rate_source
- is_sold_out / availability_source
- place_id
- google_maps_url / google_maps_search_url
- map_status / map_source / map_error / map_retry_count
- details_status / details_source / details_error / details_retry_count
- pricing_status / pricing_source / pricing_error / pricing_retry_count
- 原始訊息文字
- 來源類型
- groupId / roomId / userId
- message id
- webhook timestamp
