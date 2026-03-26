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

## 執行地圖解析 job

把已經收進 MongoDB 的住宿連結補上名稱、地址、座標與 Google Maps URL：

```bash
python -m app.map_enrichment_job
```

這支 command 適合掛進 cron，定期掃描 `map_status = pending` 的文件。

可調整的環境變數：

- `MAP_ENRICHMENT_BATCH_SIZE=20`
- `MAP_ENRICHMENT_REQUEST_TIMEOUT=10.0`
- `MAP_ENRICHMENT_MAX_RETRY_COUNT=3`

## Swagger 觸發地圖解析

如果你暫時不想設定 cron，可以直接開 Swagger 呼叫：

- `GET /jobs/map-enrichment/documents`
- `POST /jobs/map-enrichment/run`
- `POST /jobs/map-enrichment/documents/{document_id}/retry`

這兩支 API 的 200 response 會統一包成：

```json
{
  "is_success": true,
  "message": "string",
  "data": {}
}
```

建議驗證順序：

1. 先用 `GET /jobs/map-enrichment/documents?status=pending&limit=20` 看目前待解析資料
2. 再呼叫 `POST /jobs/map-enrichment/run`，可在 body 傳 `{"limit": 5}`
3. 最後再用 `GET /jobs/map-enrichment/documents?status=resolved&limit=20` 看是否出現 `property_name`、`latitude`、`longitude`、`google_maps_url`、`map_source`
4. 若只想重跑單筆文件，可直接呼叫 `POST /jobs/map-enrichment/documents/{document_id}/retry`

如果資料解析失敗，可以用 `GET /jobs/map-enrichment/documents?status=failed&limit=20` 檢查 `map_error`

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

## 目前資料格式

每擷取到一筆住宿連結，就會寫入 MongoDB `captured_lodging_links` collection，欄位包含：

- 平台
- 原始連結
- hostname
- resolved_url / resolved_hostname
- property_name / formatted_address
- latitude / longitude
- place_id
- google_maps_url
- map_status / map_source / map_error / map_retry_count
- 原始訊息文字
- 來源類型
- groupId / roomId / userId
- message id
- webhook timestamp
