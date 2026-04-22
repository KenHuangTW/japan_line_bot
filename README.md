# Nihon LINE Bot

Nihon LINE Bot 是一個用 FastAPI 實作的 LINE webhook 服務，目標是讓每個 LINE 聊天室先切到「目前旅次」，再把聊天裡出現的住宿連結收進 MongoDB、補齊住宿頁地圖與價格資訊，並直接從 Mongo canonical data 產生 `/清單` preview、只讀旅次頁與 `/摘要` AI 決策摘要。Notion 仍然保留，但定位改成可選的 export / manual maintenance surface，而不是主要瀏覽介面。

目前支援的主流程：

1. 驗證 LINE webhook 簽章。
2. 從群組、多人聊天室或私聊文字訊息擷取住宿連結。
3. 先解析目前聊天室的 active trip；沒有 active trip 時會拒收住宿連結。
4. 只保留支援的 Booking.com / Agoda / Airbnb 住宿頁，必要時先解析分享短網址。
5. 以目前旅次範圍做重複判斷後寫入 MongoDB。
6. 透過 enrichment job 補上名稱、地址、座標、設備、價格與 Google Maps 連結。
7. `/清單` 會直接從 Mongo canonical data 回傳旅次 preview，並附上只讀旅次頁連結。
8. `/摘要` 會直接根據目前旅次的 canonical lodging payload 呼叫 Gemini，回傳候選住宿、優缺點、待補資訊與討論重點。
9. 透過 Notion sync job 將資料建立或更新到旅次對應的 Notion data source；若有設定 target，旅次頁也會提供 Notion 匯出捷徑。

## 功能重點

- 支援 `booking.com`、`agoda.com`、`airbnb.com` 住宿連結。
- 支援 Agoda / Booking 分享短網址解析後再判斷是否為住宿頁。
- 每個 LINE 聊天室都可以建立、切換、查詢與封存 active trip。
- 同一聊天室內只在同一個旅次判定重複；不同旅次可保留相同房源。
- 可選擇把旅次相關指令與住宿連結收錄從控制聊天室 A 代理到被控制聊天室 B，方便私下操作正式群組資料。
- 提供 mobile-friendly 的只讀旅次頁，直接從 Mongo 顯示候選住宿與住宿縮圖，支援基本篩選與排序。
- `/清單` 會回 LINE Flex carousel，每筆候選住宿一張卡片；若 Mongo 已存好 `line_hero_image_url`，會直接顯示 hero image，再引導到房源頁與旅次詳情頁。
- `/摘要` 會以 Gemini structured output 回傳目前旅次的候選住宿、優缺點、缺漏資訊與討論重點。
- 可選擇在成功收錄或發現重複連結時直接回覆 LINE。
- 提供住宿 enrichment API 與 Notion sync API，方便手動觸發或串接排程。
- 提供 `/help`、`/ping`、`/建立旅次`、`/切換旅次`、`/目前旅次`、`/封存旅次`、`/清單`、`/摘要`、`/整理`、`/全部重來` 十個 LINE 指令。
- 提供 shell / PowerShell 腳本協助啟動 MongoDB、服務與測試。

旅次顯示層與 AI 摘要的操作說明，請參考 [docs/trip-display-surface.md](docs/trip-display-surface.md) 與 [docs/lodging-decision-summary.md](docs/lodging-decision-summary.md)。
AI workflow skill 的共用版與 local overlay 規則，請參考 [docs/ai-skills.md](docs/ai-skills.md)。

## 資料流程

```text
LINE message
  -> /webhooks/line
  -> validate signature
  -> resolve active trip
  -> extract lodging URLs
  -> resolve share links
  -> dedupe within the same trip
  -> MongoDB captured_lodging_links
  -> /清單 LINE preview
  -> /trips/{display_token} read-only trip detail surface
  -> /摘要 Gemini decision summary
  -> lodging enrichment job
  -> optional Notion sync job
  -> trip-scoped Notion data source (optional export)
```

## 專案結構

```text
app/
  controllers/         Webhook / job controller 與 repository adapter
  lodging_summary/     Gemini client、AI 摘要 service 與 LINE rendering
  lodging_links/       Booking / Agoda 網址分類與短網址解析流程
  map_enrichment/      住宿頁地圖、地址、價格、設備資料解析
  models/              MongoDB 文件與共用 model
  notion_sync/         Notion data source 建立與同步邏輯
  routers/             FastAPI 路由
  schemas/             API request / response schema
  trip_display/        旅次顯示層的 query model、rendering 與 Mongo aggregation
  collector.py         MongoDB collector 建立
  config.py            環境變數設定
  main.py              FastAPI app 組裝入口
tests/                 單元測試與 API / webhook 測試
docs/                  操作說明與產品行為文件
.codex/skills/         Codex 共用 workflow skills；本機 override 請用 *.local
.windsurf/             Windsurf 共用 skills / workflows；本機 override 請用 *.local
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
- 若要使用 `/摘要`：Gemini Developer API key
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

如果你要啟用 `/摘要` AI 決策摘要，另外需要：

- `GEMINI_API_KEY`

如果你想在安靜的控制聊天室 A 私下操作另一個正式群組 B，可另外設定：

- `LINE_COMMAND_CONTROL_SOURCE_GROUP_ID`
- `LINE_COMMAND_CONTROL_TARGET_GROUP_ID`

啟用後，`/建立旅次`、`/切換旅次`、`/目前旅次`、`/封存旅次`、`/清單`、`/摘要`、`/整理`、`/全部重來` 會改作用在 B 的 group scope；但你在 A 直接貼 Booking / Agoda / Airbnb 連結時，系統仍然只看 A 自己的 active trip，不會偷偷寫進 B。
啟用後，`/建立旅次`、`/切換旅次`、`/目前旅次`、`/封存旅次`、`/清單`、`/摘要`、`/整理`、`/全部重來`，以及你在 A 貼出的 Booking / Agoda / Airbnb 住宿連結，都會改作用在 B 的 group scope。LINE 回覆仍然會回在 A，但 active trip、duplicate lookup、capture 儲存與後續 sync 都以 B 為準。

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
| `TRIP_COLLECTION` | `line_trips` | 旅次狀態與 active trip collection。 |

### LINE webhook 與回覆

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `LINE_CHANNEL_SECRET` | 空字串 | 驗證 `X-Line-Signature`。 |
| `LINE_CHANNEL_ACCESS_TOKEN` | 空字串 | 發送 LINE reply message。留空時仍可收資料，但無法回覆。 |
| `LINE_COMMAND_CONTROL_SOURCE_GROUP_ID` | 空字串 | 可選。控制聊天室 A 的 LINE `groupId`；當旅次相關指令或住宿連結從這個群組發出時，資料流程會改導向 target group。 |
| `LINE_COMMAND_CONTROL_TARGET_GROUP_ID` | 空字串 | 可選。被控制聊天室 B 的 LINE `groupId`；需與 `LINE_COMMAND_CONTROL_SOURCE_GROUP_ID` 一起設定才會生效。 |
| `LINE_REPLY_ON_CAPTURE` | `true` | 收錄成功時是否回覆「已收到 N 筆住宿連結」。 |
| `LINE_WELCOME_MESSAGE` | `已加入群組。請先用 /建立旅次 <名稱> 建立目前旅次，再貼 Booking、Agoda 或 Airbnb 的住宿連結。` | bot 加入群組時的歡迎訊息。 |
| `REPLY_CAPTURE_TEMPLATE` | `已收到 {count} 筆住宿連結，會自動整理並同步到 Notion。` | 成功收錄回覆模板。 |
| `REPLY_DUPLICATE_LINK_TEMPLATE` | `你是不是在找這個\n{url}` | 重複連結回覆模板。 |
| `SUPPORTED_DOMAINS` | `booking.com,agoda.com,airbnb.com,airbnb.com.tw` | 允許擷取的 domain 清單，逗號分隔。 |

`LINE_COMMAND_CONTROL_SOURCE_GROUP_ID` 與 `LINE_COMMAND_CONTROL_TARGET_GROUP_ID` 會同時影響旅次相關指令與住宿連結收錄範圍；但 LINE reply 仍然留在控制聊天室 A。

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
| `NOTION_DATABASE_URL` | 空字串 | 資料庫 URL 快取，可選填，供 Notion target 校正或 fallback 使用。 |
| `NOTION_PUBLIC_DATABASE_URL` | 空字串 | 公開分享 URL 快取，可選填，供 Notion export target 使用。 |
| `NOTION_TARGET_COLLECTION` | `notion_targets` | 儲存聊天室對 Notion target 映射的 Mongo collection。 |
| `NOTION_API_VERSION` | `2026-03-11` | Notion API version header。 |
| `NOTION_REQUEST_TIMEOUT` | `10.0` | Notion HTTP request timeout。 |
| `NOTION_SYNC_BATCH_SIZE` | `20` | API / job 預設一次同步幾筆。 |

### Gemini AI 摘要

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 空字串 | Gemini Developer API key；未設定時 `/摘要` 會回覆尚未設定完成。 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | `/摘要` 使用的 Gemini model。 |
| `GEMINI_REQUEST_TIMEOUT` | `15.0` | 呼叫 Gemini 產生 structured summary 的 timeout。 |

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
- Airbnb 住宿頁。

### 連結處理規則

- 先用 regex 從訊息中抓出 `http://` 或 `https://` URL。
- 只保留 `SUPPORTED_DOMAINS` 允許的 host。
- Agoda / Booking 若是短網址，會先 follow redirect。
- 只有最終確認是住宿頁才會進入後續流程；活動頁、非房源頁或解析失敗的短網址會被忽略。

### 重複判斷規則

- 只在同一個 LINE source scope 的同一個 active trip 內判定重複：
  - `group` 以 `group_id + trip_id`
  - `room` 以 `room_id + trip_id`
  - `user` 以 `user_id + trip_id`
- 會同時比對原始 `url` 與 `resolved_url`。
- 會將等價住宿網址正規化後比對，避免 query string 或追蹤參數造成重複。
- 如果已存的是短網址，回覆重複時會優先回短網址；如果本次傳入的是短網址，也會優先回本次短網址。
- 同一個房源若切到不同旅次，會被視為新的旅次資料。

## LINE 指令

| 指令 | 說明 |
| --- | --- |
| `/help` | 顯示目前支援的指令與說明。 |
| `/ping` | 回覆 `pong`。 |
| `/建立旅次 <名稱>` | 建立新旅次並切換為目前旅次。 |
| `/切換旅次 <名稱>` | 切換到同一聊天室內既有、未封存的旅次。 |
| `/目前旅次` | 查看目前啟用中的旅次名稱與旅次 ID。 |
| `/封存旅次` | 封存目前旅次，並清空 active trip。 |
| `/清單` | 回傳目前旅次的 LINE Flex carousel；每張卡片可點圖文開房源，並提供 `已訂這間` / `改回候選` 與旅次詳情入口。 |
| `/摘要` | 根據目前旅次的 canonical lodging payload 呼叫 Gemini，回傳候選住宿、優缺點、待補資訊與討論重點。 |
| `/整理` | 只針對目前旅次範圍，先跑 lodging enrichment，再同步 pending / failed / 有更新的資料到 Notion。 |
| `/全部重來` | 只針對目前旅次範圍，忽略既有同步狀態，先重跑 enrichment，再強制同步所有資料到 Notion；若有預設 Notion parent page，也會自動建立該旅次的 target。 |

注意：

- 貼住宿連結前必須先有 active trip，否則 bot 只會回覆旅次建立 / 切換提示，不會收錄資料。
- `/清單`、`/摘要`、`/整理`、`/全部重來` 都必須能辨識目前 source scope，且該聊天室要先有 active trip。
- `已訂這間`、`改回候選`、`不考慮這間` 都是使用者決策狀態；這和來源網站解析出的 `可訂`、`已售完`、`待確認` 是兩組不同資訊。
- Notion target 未設定完成時，`/清單` 仍可正常顯示 Mongo preview 與旅次頁，但不會出現 Notion 匯出捷徑；`/整理`、`/全部重來` 仍需要 Notion sync 設定。
- `GEMINI_API_KEY` 未設定時，`/摘要` 會回覆 `AI 摘要尚未設定完成。`。
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

### 3. Trip display

| Method | Path | 說明 |
| --- | --- | --- |
| `GET` | `/trips/{display_token}` | 手機友善的旅次頁，直接從 Mongo 顯示住宿，支援 `platform`、`availability`、`decision_status`、`sort` query 參數。 |
| `POST` | `/trips/{display_token}/lodgings/{document_id}/decision` | 從旅次頁更新單筆住宿決策狀態，可用於 `不考慮這間` 或 `改回候選`。 |

行為說明：

- `display_token` 是穩定的旅次分享 token，不會暴露 raw `group_id` / `room_id` / `user_id`。
- token 有效時，頁面會顯示住宿縮圖、名稱、平台、價格、可訂狀態、使用者決策狀態、地圖連結與 Notion 匯出捷徑（若該旅次有 target）。
- 住宿卡片優先使用 `hero_image_url` 作為網頁縮圖，缺圖時會顯示固定尺寸 fallback，不影響卡片操作。
- 預設會顯示 `候選中` 與 `已預訂`，隱藏 `不考慮`；需要整理或復原時可用 `decision_status=dismissed` 篩選。
- token 無效時，會回 `404 Invalid trip display link.`。

### 4. Lodging enrichment API

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

### 5. Notion sync API

Swagger tag 為 `notion-sync`。

前置條件：

- `POST /jobs/notion-sync/setup` 一律需要 `NOTION_API_TOKEN`
- 若是設定全域 default target，還需要以下兩者擇一：
  - `NOTION_PARENT_PAGE_ID`，用來建立新的 database
  - `NOTION_DATA_SOURCE_ID`，用來直接校正既有 data source schema
- 若是設定特定旅次 target，可在 request body 直接提供 `source_type` + chat id + `trip_id`，再搭配 `parent_page_id` 或 `data_source_id`
- `POST /jobs/notion-sync/run` 需要 `NOTION_API_TOKEN` 與可用的 default/scoped target

| Method | Path | 說明 |
| --- | --- | --- |
| `POST` | `/jobs/notion-sync/setup` | 建立或校正全域或旅次專屬的 Notion database / data source schema。 |
| `POST` | `/jobs/notion-sync/run` | 同步 pending / failed / 有更新的文件到 Notion，可指定旅次範圍。 |
| `GET` | `/jobs/notion-sync/documents` | 列出 Notion sync 狀態，可用聊天室 scope 與 `trip_id` 過濾。 |
| `POST` | `/jobs/notion-sync/documents/{document_id}/retry` | 單筆文件重跑同步。 |

`POST /jobs/notion-sync/setup` request body 可選填：

```json
{
  "title": "Trip Lodgings"
}
```

若要設定某個旅次專屬 target，可以改成：

```json
{
  "title": "Tokyo 2026 Lodgings",
  "source_type": "group",
  "group_id": "Cgroup123",
  "trip_id": "trip-current",
  "trip_title": "東京 2026",
  "parent_page_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
}
```

或綁定既有 data source：

```json
{
  "source_type": "room",
  "room_id": "Rroom123",
  "trip_id": "trip-current",
  "data_source_id": "ffffffff-1111-2222-3333-444444444444"
}
```

setup 成功後會回傳：

- `database_id`
- `data_source_id`
- `database_url`
- `database_public_url`
- `target_source`
- `source_type` / `group_id` / `room_id` / `user_id`
- `trip_id` / `trip_title`

如果回傳的是全域 default target，建議把 `database_id`、`data_source_id` 視需要回填到 `.env`。旅次專屬 target 會存進 `NOTION_TARGET_COLLECTION`，不需要再寫回 `.env`。

`POST /jobs/notion-sync/run` request body：

```json
{
  "limit": 20,
  "force": false
}
```

若要只跑某個旅次，可以加上 source scope 與 `trip_id`：

```json
{
  "limit": 20,
  "force": true,
  "source_type": "group",
  "group_id": "Cgroup123",
  "trip_id": "trip-current",
  "trip_title": "東京 2026"
}
```

`force` 行為：

- `false`：只同步 pending、failed、或在上次同步後又被 capture / enrichment 更新的文件。
- `true`：忽略同步狀態，重跑所有文件；若 `data_source_id` 已存在，也會先校正 schema。

`GET /jobs/notion-sync/documents` 除了 `limit` 與 `status`，也可帶：

- `source_type=group&group_id=...`
- `source_type=room&room_id=...`
- `source_type=user&user_id=...`
- `trip_id=...`

### Notion data source 欄位

setup 後會收斂成以下 8 個欄位：

- `名稱`
- `平台`
- `房源URL`
- `Google 地圖 URL`
- `設施`
- `決策狀態`
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

這個 job 會依每筆文件的 source scope + trip scope 決定使用旅次專屬 target 或全域 default target；但若文件帶有 `trip_id`，就必須有對應的 trip-scoped target 才會同步。

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

### 住宿決策狀態

- `decision_status`
- `decision_updated_at`
- `decision_updated_by_user_id`

`decision_status` 預設為 `candidate`，可被使用者改成 `booked` 或 `dismissed`。這是旅次討論中的主觀決策，不代表來源平台的供應狀態；來源平台狀態仍由 `is_sold_out` / `availability_source` 表示。

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
- Mongo 是旅次顯示層的 source of truth；Notion target 只會影響 export / sync，不影響 `/清單` 與 `/trips/{display_token}` 的主顯示流程。
- `/摘要` 直接重用 `app.trip_display` 的 canonical payload，不會另外重查原始聊天紀錄或 Notion rich text。
- 若你在 Notion 建好 data source 後想長期固定使用同一份全域資料，建議把 setup 回傳的 id 回填到 `.env`。
- 若你要開始規劃新旅次，先在 LINE 用 `/建立旅次 <名稱>` 建立 active trip，再為該旅次呼叫 scoped `POST /jobs/notion-sync/setup`，或直接執行 `/全部重來` 讓系統建立 trip-scoped target。
- 若要調整 AI 摘要 prompt、schema 或 fallback 行為，請優先看 [docs/lodging-decision-summary.md](docs/lodging-decision-summary.md) 與 `app/lodging_summary/`。
