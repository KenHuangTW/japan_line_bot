# Nihon LINE Bot

這是一個用 FastAPI 實作的 LINE bot webhook MVP，先專注把「群組丟出 Booking / Agoda 住宿連結」這件事收進系統。

目前功能：

- 驗證 LINE webhook 簽章
- 接收群組或私聊的文字訊息
- 擷取 `booking.com` / `agoda.com` 連結
- 先把結果落在本機 `JSONL` 檔案，方便之後接 HackMD、Google Sheet 或資料庫
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

目前暫存輸出會寫到 `data/captured_lodging_links.jsonl`。

## 啟動服務

```bash
uvicorn app.main:app --reload
```

健康檢查：

```bash
curl http://127.0.0.1:8000/healthz
```

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

每擷取到一筆住宿連結，就會寫一行 JSON，內容包含：

- 平台
- 原始連結
- hostname
- 原始訊息文字
- 來源類型
- groupId / roomId / userId
- message id
- webhook timestamp

## 下一步建議

現在這版先把 LINE bot 主幹打通。下一階段可以二選一：

1. 接 HackMD API，把 JSONL 同步成一篇整理筆記
2. 改成先寫 SQLite / Google Sheet，再讓 HackMD 只負責展示
