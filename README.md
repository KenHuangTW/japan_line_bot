# Nihon LINE Bot

這是一個用 FastAPI 實作的 LINE bot webhook MVP，先專注把「群組丟出 Booking / Agoda 住宿連結」這件事收進系統。

目前功能：

- 驗證 LINE webhook 簽章
- 接收群組或私聊的文字訊息
- 擷取 `booking.com` / `agoda.com` 連結
- 預設把住宿連結寫進 MongoDB，保留 `JSONL` fallback 方便測試或離線開發
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
  models.py
Dockerfile
docker-compose.yml
mongo.sh
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

## 設定環境變數

先複製一份設定檔：

```bash
cp .env.example .env
```

你至少要填這兩個值：

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`

預設資料儲存設定如下：

- `STORAGE_BACKEND=mongo`
- `MONGO_URI=mongodb://127.0.0.1:27017`
- `MONGO_DATABASE=nihon_line_bot`
- `MONGO_COLLECTION=captured_lodging_links`

如果你暫時不想跑 MongoDB，也可以把 `STORAGE_BACKEND=jsonl`，此時會改寫到 `COLLECTOR_OUTPUT_PATH`。

## 啟動 MongoDB

本機用 Docker 跑 MongoDB：

```bash
./mongo.sh
```

你也可以看 log 或停止服務：

```bash
./mongo.sh logs
./mongo.sh down
```

## 啟動服務

```bash
./start.sh
```

健康檢查：

```bash
curl http://127.0.0.1:8000/healthz
```

執行測試：

```bash
./test.sh
```

如果你已經把本機服務跑起來，想直接做一筆 webhook smoke test：

```bash
./test.sh smoke
```

你也可以用環境變數改 host / port / conda env：

```bash
HOST=0.0.0.0 PORT=8001 CONDA_ENV_NAME=nihon-line-bot ./start.sh
```

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
- 原始訊息文字
- 來源類型
- groupId / roomId / userId
- message id
- webhook timestamp

如果切到 `jsonl` fallback，資料格式會維持一行一筆 JSON，欄位內容相同。
