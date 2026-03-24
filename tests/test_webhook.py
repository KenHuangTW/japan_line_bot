from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.collector import JsonlCollector
from app.config import Settings
from app.line_security import generate_signature
from app.main import create_app


class FakeLineClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def reply_text(self, reply_token: str, text: str) -> None:
        self.calls.append((reply_token, text))


def _build_payload(message_text: str) -> dict[str, object]:
    return {
        "destination": "Ubot",
        "events": [
            {
                "type": "message",
                "replyToken": "reply-token",
                "mode": "active",
                "timestamp": 1711111111111,
                "source": {
                    "type": "group",
                    "groupId": "Cgroup123",
                    "userId": "Uuser123",
                },
                "message": {
                    "id": "325708",
                    "type": "text",
                    "text": message_text,
                },
            }
        ],
    }


def test_line_webhook_captures_links_and_replies(tmp_path: Path) -> None:
    output_path = tmp_path / "captured.jsonl"
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        collector_output_path=output_path,
    )
    fake_line_client = FakeLineClient()
    app = create_app(
        settings=settings,
        collector=JsonlCollector(output_path),
        line_client=fake_line_client,
    )
    client = TestClient(app)

    payload = _build_payload(
        (
            "候選住宿有 "
            "https://www.booking.com/hotel/jp/foo.html "
            "和 https://www.agoda.com/zh-tw/bar-hotel.html "
            "還有 https://example.com/ignore"
        )
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 2}

    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["platform"] for row in rows] == ["booking", "agoda"]
    assert all(row["group_id"] == "Cgroup123" for row in rows)
    assert fake_line_client.calls == [
        ("reply-token", "已收到 2 筆住宿連結，先幫你記下來了。")
    ]


def test_line_webhook_rejects_invalid_signature(tmp_path: Path) -> None:
    output_path = tmp_path / "captured.jsonl"
    settings = Settings(
        line_channel_secret="super-secret",
        collector_output_path=output_path,
    )
    client = TestClient(create_app(settings=settings))

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    response = client.post(
        "/webhooks/line",
        json=payload,
        headers={"X-Line-Signature": "bad-signature"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid LINE signature."
