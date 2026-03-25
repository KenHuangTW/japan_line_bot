param(
    [ValidateSet("unit", "smoke")]
    [string]$Mode = "unit",
    [string]$CondaEnvName = ""
)

$ErrorActionPreference = "Stop"

$RootDir = $PSScriptRoot
if (-not $RootDir) {
    $RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not $CondaEnvName) {
    $CondaEnvName = if ($env:CONDA_ENV_NAME) { $env:CONDA_ENV_NAME } else { "nihon-line-bot" }
}

Set-Location $RootDir

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "conda is required but was not found in PATH."
}

if ($Mode -eq "unit") {
    & conda run --no-capture-output -n $CondaEnvName pytest -q
    exit $LASTEXITCODE
}

$SmokeTestScript = @'
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pymongo import MongoClient

from app.config import Settings

settings = Settings.from_env()
health_url = "http://127.0.0.1:8000/healthz"
webhook_url = "http://127.0.0.1:8000/webhooks/line"

if not settings.line_channel_secret:
    print("LINE_CHANNEL_SECRET is missing.", file=sys.stderr)
    raise SystemExit(1)

try:
    with urlopen(health_url, timeout=5) as response:
        print("Health check:", response.read().decode("utf-8"))
except URLError as exc:
    print(
        "Server is not reachable on http://127.0.0.1:8000. Run .\\start.ps1 first.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
test_url = "https://www.booking.com/hotel/jp/smoke-test.html"
message_id = f"smoke-{timestamp_ms}"
payload = {
    "destination": "U-smoke-test",
    "events": [
        {
            "type": "message",
            "replyToken": "smoke-test-reply-token",
            "mode": "active",
            "timestamp": timestamp_ms,
            "source": {
                "type": "group",
                "groupId": "C-smoke-test-group",
                "userId": "U-smoke-test-user",
            },
            "message": {
                "id": message_id,
                "type": "text",
                "text": f"smoke test {test_url}",
            },
        }
    ],
}

mongo_client = MongoClient(settings.mongo_uri, tz_aware=True)
collection = mongo_client[settings.mongo_database][settings.mongo_collection]
before_count = collection.count_documents({})

body = json.dumps(payload).encode("utf-8")
signature = base64.b64encode(
    hmac.new(
        settings.line_channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
).decode("utf-8")

request = Request(
    webhook_url,
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Line-Signature": signature,
    },
    method="POST",
)

try:
    with urlopen(request, timeout=10) as response:
        response_body = response.read().decode("utf-8")
except HTTPError as exc:
    print(f"Webhook request failed with {exc.code}", file=sys.stderr)
    print(exc.read().decode("utf-8"), file=sys.stderr)
    raise SystemExit(1) from exc

after_count = collection.count_documents({})
latest_row = collection.find_one({"message_id": message_id})
mongo_client.close()

if latest_row is None:
    print("MongoDB did not store the smoke test document.", file=sys.stderr)
    raise SystemExit(1)

if latest_row["url"] != test_url:
    print("Stored MongoDB document does not contain the smoke test URL.", file=sys.stderr)
    raise SystemExit(1)

latest_row = json.dumps(latest_row, default=str, ensure_ascii=False)

if after_count != before_count + 1:
    print(
        f"Expected stored rows to grow by 1, got before={before_count}, after={after_count}.",
        file=sys.stderr,
    )
    raise SystemExit(1)

print("Webhook response:", response_body)
print(f"Stored rows: {before_count} -> {after_count}")
print(f"Latest record: {latest_row}")
'@

& conda run --no-capture-output -n $CondaEnvName python -c $SmokeTestScript
exit $LASTEXITCODE
