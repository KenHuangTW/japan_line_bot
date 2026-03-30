# Nihon LINE Bot

Nihon LINE Bot 是一個用 FastAPI 實作的 LINE webhook 服務，目標是把聊天裡出現的住宿連結收進 MongoDB，補齊住宿頁地圖與價格資訊，再同步到 Notion。

目前支援的主流程：

1. 驗證 LINE webhook 簽章。
2. 從群組、多人聊天室或私聊文字訊息擷取住宿連結。
3. 只保留支援的 Booking.com / Agoda 住宿頁，必要時先解析分享短網址。
4. 以聊天室範圍做重複判斷後寫入 MongoDB。
5. 透過 enrichment job 補上名稱、地址、座標、設備、價格與 Google Maps 連結。
6. 透過 Notion sync job 將資料建立或更新到 Notion data source。

## 功能重點

- 支援 `booking.com` 與 `agoda.com` 住宿連結。
- 支援 Agoda / Booking 分享短網址解析後再判斷是否為住宿頁。
- 同一聊天室內會偵測重複連結，避免重複收錄。
- 可選擇在成功收錄或發現重複連結時直接回覆 LINE。
- 提供住宿 enrichment API 與 Notion sync API，方便手動觸發或串接排程。
- 提供 `/help`、`/ping`、`/清單`、`/整理`、`/全部重來` 五個 LINE 指令。
- 提供 shell / PowerShell 腳本協助啟動 MongoDB、服務與測試。

## 資料流程

```text
LINE message
  -> /webhooks/line
  -> validate signature
  -> extract lodging URLs
  -> resolve share links
  -> dedupe within the same chat scope
  -> MongoDB captured_lodging_links
  -> lodging enrichment job
  -> Notion sync job
  -> Notion data source
```

## 專案結構

```text
app/
  controllers/         Webhook / job controller 與 repository adapter
  lodging_links/       Booking / Agoda 網址分類與短網址解析流程
  map_enrichment/      住宿頁地圖、地址、價格、設備資料解析
  models/              MongoDB 文件與共用 model
  notion_sync/         Notion data source 建立與同步邏輯
  routers/             FastAPI 路由
  schemas/             API request / response schema
  collector.py         MongoDB collector 建立
  config.py            環境變數設定
  main.py              FastAPI app 組裝入口
tests/                 單元測試與 API / webhook 測試
Dockerfile             單容器部署設定
docker-compose.yml     server + MongoDB 本機整套啟動
start.sh / start.ps1   啟動 FastAPI
mongo.sh / mongo.ps1   啟停 MongoDB container
test.sh / test.ps1     單元測試與 smoke test
```

## 執行需求

- Python 3.11
- MongoDB 7.0 以上，或用 Docker Compose 啟動內建 MongoDB
- LINE Messaging API channel
- 若要同步 Notion：Notion integration token 與可寫入的 parent page / data source
- 若要使用 `start.sh` / `test.sh`：本機需有 conda

## 快速開始

### 1. 建立環境

使用 conda：

```bash
conda env create -f environment.yml
conda activate nihon-line-bot
```

如果你不使用 conda，也可以直接安裝：

```bash
python3 -m pip install -e .[dev]
```

Windows PowerShell：

```powershell
python -m pip install -e '.[dev]'
```

### 2. 建立 `.env`

repo 已提供 `.env.example`。先複製一份：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

最少需要先填：

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`

如果只想先測 webhook 收錄到 MongoDB，不做 Notion sync，Notion 相關設定可以先留空。

### 3. 啟動 MongoDB

本機只啟 MongoDB：

```bash
./mongo.sh
```

Windows PowerShell：

```powershell
.\mongo.ps1
```

其他常用動作：

```bash
./mongo.sh logs
./mongo.sh restart
./mongo.sh down
```

Windows PowerShell：

```powershell
.\mongo.ps1 logs
.\mongo.ps1 restart
.\mongo.ps1 down
```

### 4. 啟動服務

使用腳本：

```bash
./start.sh
```

Windows PowerShell：

```powershell
.\start.ps1
```

如果你不是用 conda，也可以直接執行：

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果你要覆寫腳本的 host / port / conda env：

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

如果 PowerShell 的 execution policy 擋住本機腳本：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

### 5. 健康檢查

```bash
curl http://127.0.0.1:8000/healthz
```

預期 response 類似：

```json
{
  "status": "ok",
  "environment": "development",
  "line_secret_configured": true,
  "line_reply_configured": true,
  "storage_target": "mongodb://127.0.0.1:27017/nihon_line_bot.captured_lodging_links"
}
```

## 環境變數

`.env.example` 放的是最小可跑設定。下面列的是目前程式支援的完整 env。

### 一般與 MongoDB

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `APP_ENV` | `development` | 環境名稱，會顯示在 `/healthz`。 |
| `MONGO_URI` | `mongodb://127.0.0.1:27017` | MongoDB connection string。 |
| `MONGO_DATABASE` | `nihon_line_bot` | 資料庫名稱。 |
| `MONGO_COLLECTION` | `captured_lodging_links` | 住宿連結 collection。 |

### LINE webhook 與回覆

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `LINE_CHANNEL_SECRET` | 空字串 | 驗證 `X-Line-Signature`。 |
| `LINE_CHANNEL_ACCESS_TOKEN` | 空字串 | 發送 LINE reply message。留空時仍可收資料，但無法回覆。 |
| `LINE_REPLY_ON_CAPTURE` | `true` | 收錄成功時是否回覆「已收到 N 筆住宿連結」。 |
| `LINE_WELCOME_MESSAGE` | `已加入群組。之後只要貼 Booking 或 Agoda 的住宿連結，我就會先幫你收下來。` | bot 加入群組時的歡迎訊息。 |
| `REPLY_CAPTURE_TEMPLATE` | `已收到 {count} 筆住宿連結，先幫你記下來了。` | 成功收錄回覆模板。 |
| `REPLY_DUPLICATE_LINK_TEMPLATE` | `你是不是在找這個\n{url}` | 重複連結回覆模板。 |
| `SUPPORTED_DOMAINS` | `booking.com,agoda.com` | 允許擷取的 domain 清單，逗號分隔。 |

### 住宿 enrichment

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `MAP_ENRICHMENT_BATCH_SIZE` | `20` | API / job 預設一次處理幾筆待解析文件。 |
| `MAP_ENRICHMENT_REQUEST_TIMEOUT` | `10.0` | 抓住宿頁與相關 HTTP request timeout。 |
| `MAP_ENRICHMENT_MAX_RETRY_COUNT` | `3` | `map_status=failed` 之後最多自動重試次數。 |

### Notion sync

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `NOTION_API_TOKEN` | 空字串 | Notion integration token。 |
| `NOTION_PARENT_PAGE_ID` | 空字串 | 第一次建立資料庫時使用的 parent page。 |
| `NOTION_DATABASE_ID` | 空字串 | 已存在的 Notion database id。 |
| `NOTION_DATA_SOURCE_ID` | 空字串 | 已存在的 Notion data source id。 |
| `NOTION_DATABASE_TITLE` | `Nihon LINE Bot Lodgings` | setup 時預設資料庫名稱。 |
| `NOTION_DATABASE_URL` | 空字串 | 資料庫 URL 快取，可選填。 |
| `NOTION_PUBLIC_DATABASE_URL` | 空字串 | 公開分享 URL 快取，可選填，`/清單` 會優先回傳它。 |
| `NOTION_API_VERSION` | `2026-03-11` | Notion API version header。 |
| `NOTION_REQUEST_TIMEOUT` | `10.0` | Notion HTTP request timeout。 |
| `NOTION_SYNC_BATCH_SIZE` | `20` | API / job 預設一次同步幾筆。 |

### 啟動腳本可覆寫的變數

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `CONDA_ENV_NAME` | `nihon-line-bot` | `start.sh` / `test.sh` 使用的 conda env 名稱。 |
| `HOST` | `127.0.0.1` | 啟動服務的 bind host。 |
| `PORT` | `8000` | 啟動服務的 port。 |
| `RELOAD` | `true` | `start.sh` / `start.ps1` 是否加上 `--reload`。 |

## 支援的連結與重複判斷規則

### 支援的連結型態

- Booking.com 住宿頁。
- Booking.com 分享短網址，例如 `https://www.booking.com/Share-08PTGo`。
- Agoda 住宿頁。
- Agoda 分享短網址，例如 `https://www.agoda.com/sp/...`。

### 連結處理規則

- 先用 regex 從訊息中抓出 `http://` 或 `https://` URL。
- 只保留 `SUPPORTED_DOMAINS` 允許的 host。
- Agoda / Booking 若是短網址，會先 follow redirect。
- 只有最終確認是住宿頁才會進入後續流程；活動頁、非房源頁或解析失敗的短網址會被忽略。

### 重複判斷規則

- 只在同一個 LINE source scope 內判定重複：
  - `group` 以 `group_id`
  - `room` 以 `room_id`
  - `user` 以 `user_id`
- 會同時比對原始 `url` 與 `resolved_url`。
- 會將等價住宿網址正規化後比對，避免 query string 或追蹤參數造成重複。
- 如果已存的是短網址，回覆重複時會優先回短網址；如果本次傳入的是短網址，也會優先回本次短網址。

## LINE 指令

| 指令 | 說明 |
| --- | --- |
| `/help` | 顯示目前支援的指令與說明。 |
| `/ping` | 回覆 `pong`。 |
| `/清單` | 回傳目前 Notion 住宿清單連結。若有 `NOTION_PUBLIC_DATABASE_URL` 會優先使用。 |
| `/整理` | 只針對目前聊天室範圍，先跑 lodging enrichment，再同步 pending / failed / 有更新的資料到 Notion。 |
| `/全部重來` | 只針對目前聊天室範圍，忽略既有同步狀態，先重跑 enrichment，再強制同步所有資料到 Notion。 |

注意：

- `/整理` 與 `/全部重來` 都必須能辨識目前 source scope，否則會回覆無法辨識聊天室。
- Notion 未設定完成時，`/清單`、`/整理`、`/全部重來` 不會成功。
- `LINE_CHANNEL_ACCESS_TOKEN` 留空時，指令仍會執行，但 bot 無法回覆訊息。

## API 總覽

### 1. Health

| Method | Path | 說明 |
| --- | --- | --- |
| `GET` | `/healthz` | 回傳目前環境、LINE 設定狀態與 Mongo 目標位置。 |

### 2. LINE webhook

| Method | Path | 說明 |
| --- | --- | --- |
| `POST` | `/webhooks/line` | LINE Messaging API webhook endpoint。 |

需求：

- header 需帶 `X-Line-Signature`
- request body 需符合 LINE webhook payload

response：

```json
{
  "ok": true,
  "captured": 1
}
```

`captured` 代表本次實際新增的文件數，不含被判定為重複的連結。

### 3. Lodging enrichment API

Swagger tag 為 `lodging-enrichment`。

| Method | Path | 說明 |
| --- | --- | --- |
| `POST` | `/jobs/lodging-enrichment/run` | 處理 pending / 可重試失敗文件。 |
| `GET` | `/jobs/lodging-enrichment/documents` | 列出文件與解析狀態。 |
| `POST` | `/jobs/lodging-enrichment/documents/retry-all` | 忽略狀態，重跑所有文件。 |
| `POST` | `/jobs/lodging-enrichment/documents/{document_id}/retry` | 單筆文件重跑。 |

舊路徑 `/jobs/map-enrichment/*` 仍可用，但不會出現在 Swagger。

這組 API 的成功 response 會包成：

```json
{
  "is_success": true,
  "message": "Lodging enrichment job finished.",
  "data": {}
}
```

`POST /jobs/lodging-enrichment/run` request body：

```json
{
  "limit": 5
}
```

常見狀態說明：

- `map_status = pending`：尚未解析地圖資訊。
- `map_status = resolved`：已取得精準座標。
- `map_status = partial`：有名稱或地址等資訊，但還沒拿到精準座標。
- `map_status = failed`：解析失敗，需查看 `map_error`。
- `details_status` / `pricing_status` 會分別標示細節與價格資料是否成功解析。

建議驗證流程：

1. `GET /jobs/lodging-enrichment/documents?status=pending&limit=20`
2. `POST /jobs/lodging-enrichment/run`，body 可傳 `{"limit": 5}`
3. `GET /jobs/lodging-enrichment/documents?status=resolved&limit=20`
4. 若需要全部重跑，呼叫 `POST /jobs/lodging-enrichment/documents/retry-all`
5. 若只要重跑單筆，呼叫 `POST /jobs/lodging-enrichment/documents/{document_id}/retry`

### 4. Notion sync API

Swagger tag 為 `notion-sync`。

前置條件：

- `POST /jobs/notion-sync/setup` 需要 `NOTION_API_TOKEN`，以及以下兩者擇一：
  - `NOTION_PARENT_PAGE_ID`，用來建立新的 database
  - `NOTION_DATA_SOURCE_ID`，用來直接校正既有 data source schema
- `POST /jobs/notion-sync/run` 需要 `NOTION_API_TOKEN` 與可用的 `NOTION_DATA_SOURCE_ID`

| Method | Path | 說明 |
| --- | --- | --- |
| `POST` | `/jobs/notion-sync/setup` | 建立或校正 Notion database / data source schema。 |
| `POST` | `/jobs/notion-sync/run` | 同步 pending / failed / 有更新的文件到 Notion。 |
| `GET` | `/jobs/notion-sync/documents` | 列出 Notion sync 狀態。 |
| `POST` | `/jobs/notion-sync/documents/{document_id}/retry` | 單筆文件重跑同步。 |

`POST /jobs/notion-sync/setup` request body 可選填：

```json
{
  "title": "Trip Lodgings"
}
```

setup 成功後會回傳：

- `database_id`
- `data_source_id`
- `database_url`
- `database_public_url`

建議把 `database_id`、`data_source_id` 視需要回填到 `.env`。

`POST /jobs/notion-sync/run` request body：

```json
{
  "limit": 20,
  "force": false
}
```

`force` 行為：

- `false`：只同步 pending、failed、或在上次同步後又被 capture / enrichment 更新的文件。
- `true`：忽略同步狀態，重跑所有文件；若 `data_source_id` 已存在，也會先校正 schema。

### Notion data source 欄位

setup 後會收斂成以下 7 個欄位：

- `名稱`
- `平台`
- `房源URL`
- `Google 地圖 URL`
- `設施`
- `最後更新時間`
- `ID`

如果已經有舊版 schema，再呼叫一次 `POST /jobs/notion-sync/setup` 也會更新成這組欄位。

## 直接執行背景 job

如果你要自己掛 cron 或排程器，可以直接跑 module。

### Lodging enrichment job

```bash
python -m app.map_enrichment_job
```

用途：

- 處理 `map_status = pending`
- 重新嘗試可重試的 `map_status = failed`
- 同步更新地圖、細節與價格欄位

### Notion sync job

```bash
python -m app.notion_sync_job
```

用途：

- 同步 `notion_sync_status = pending`
- 同步先前失敗文件
- 同步在前次成功同步後又被 capture / enrichment 更新過的文件

## 測試

### 單元測試

```bash
./test.sh
```

Windows PowerShell：

```powershell
.\test.ps1
```

上面等同於：

```bash
./test.sh unit
```

### Smoke test

先確認這幾件事：

1. MongoDB 已啟動。
2. FastAPI 服務已啟動在 `http://127.0.0.1:8000`。
3. `.env` 中已設定 `LINE_CHANNEL_SECRET`。

然後執行：

```bash
./test.sh smoke
```

Windows PowerShell：

```powershell
.\test.ps1 smoke
```

smoke test 會：

- 先呼叫 `/healthz`
- 模擬送一筆合法 LINE webhook
- 驗證 MongoDB 有沒有真的存進新文件

## Docker 用法

### 只啟 MongoDB

```bash
./mongo.sh
```

### 一次啟整套服務

```bash
docker compose up --build
```

`docker-compose.yml` 會啟兩個 service：

- `server`：對外提供 `http://127.0.0.1:8000`
- `mongo`：對外提供 `mongodb://127.0.0.1:27017`

注意：

- compose 會讀取 repo 根目錄的 `.env`
- container 內 `MONGO_URI` 會自動改成 `mongodb://mongo:27017`

## LINE Developers Console 設定

1. 建立一個 Messaging API channel。
2. 開啟 `Allow bot to join group chats`。
3. 把 webhook URL 指到公開 HTTPS 位址，例如：

```text
https://<your-domain>/webhooks/line
```

4. 啟用 webhook。
5. 把 bot 邀進目標群組或聊天室。

如果本機開發沒有公開網址，可用 Cloudflare Tunnel、ngrok 等 tunnel 工具。

## MongoDB 文件欄位

每筆收錄的住宿文件都會寫進 `captured_lodging_links` collection。主要欄位可分成這幾類。

### 原始連結與訊息來源

- `platform`
- `url`
- `hostname`
- `resolved_url`
- `resolved_hostname`
- `message_text`
- `source_type`
- `destination`
- `group_id`
- `room_id`
- `user_id`
- `message_id`
- `event_timestamp_ms`
- `event_mode`
- `captured_at`

### 地理位置與地址

- `property_name`
- `formatted_address`
- `street_address`
- `district`
- `city`
- `region`
- `postal_code`
- `country_name`
- `country_code`
- `latitude`
- `longitude`
- `place_id`
- `google_maps_url`
- `google_maps_search_url`

### 住宿細節與價格

- `property_type`
- `room_count`
- `bedroom_count`
- `bathroom_count`
- `amenities`
- `price_amount`
- `price_currency`
- `source_price_amount`
- `source_price_currency`
- `price_exchange_rate`
- `price_exchange_rate_source`
- `is_sold_out`
- `availability_source`

### Enrichment 狀態

- `map_source`
- `map_status`
- `map_error`
- `map_retry_count`
- `map_last_attempt_at`
- `map_resolved_at`
- `details_source`
- `details_status`
- `details_error`
- `details_retry_count`
- `details_last_attempt_at`
- `details_resolved_at`
- `pricing_source`
- `pricing_status`
- `pricing_error`
- `pricing_retry_count`
- `pricing_last_attempt_at`
- `pricing_resolved_at`

### Notion sync 狀態

- `notion_page_id`
- `notion_page_url`
- `notion_database_id`
- `notion_data_source_id`
- `notion_sync_status`
- `notion_sync_error`
- `notion_sync_retry_count`
- `notion_last_attempt_at`
- `notion_last_synced_at`

## 常用指令整理

```bash
# 建立 conda env
conda env create -f environment.yml
conda activate nihon-line-bot

# 啟 MongoDB
./mongo.sh

# 啟服務
./start.sh

# 跑單元測試
./test.sh

# 跑 smoke test
./test.sh smoke

# 手動跑 lodging enrichment
python -m app.map_enrichment_job

# 手動跑 Notion sync
python -m app.notion_sync_job
```

## 開發備註

- `start.sh` / `start.ps1` 會要求 `.env` 存在，否則不會啟動。
- `LINE_CHANNEL_ACCESS_TOKEN` 留空時，系統仍可驗證 webhook 並寫入 MongoDB，但所有 reply message 都會失效。
- `NOTION_PUBLIC_DATABASE_URL` 是 `/清單` 最直接的回覆來源；如果沒填，系統會嘗試從 Notion service 讀取資料庫 URL。
- 若你在 Notion 建好 data source 後想長期固定使用同一份資料，建議把 setup 回傳的 id 回填到 `.env`。
