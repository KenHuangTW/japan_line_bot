from __future__ import annotations

import json
from typing import Sequence

from fastapi.testclient import TestClient

from app.config import Settings
from app.lodging_links.service import LodgingLinkService
from app.line_security import generate_signature
from app.main import create_app
from app.models import CapturedLodgingLink


class FakeLineClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def reply_text(self, reply_token: str, text: str) -> None:
        self.calls.append((reply_token, text))


class FailingLineClient:
    async def reply_text(self, reply_token: str, text: str) -> None:
        raise RuntimeError("simulated LINE reply failure")


class FakeLodgingUrlResolver:
    def __init__(self, resolved_urls: dict[str, str | None] | None = None) -> None:
        self.resolved_urls = resolved_urls or {}
        self.calls: list[str] = []

    async def resolve(self, url: str) -> str | None:
        self.calls.append(url)
        return self.resolved_urls.get(url)


class InMemoryCapturedLinkRepository:
    def __init__(self) -> None:
        self.items: list[CapturedLodgingLink] = []

    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        self.items.extend(items)
        return len(items)


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


def test_line_webhook_captures_links_and_replies() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    app = create_app(
        settings=settings,
        collector=repository,
        line_client=fake_line_client,
        lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
    )
    client = TestClient(app)

    payload = _build_payload(
        (
            "候選住宿有 "
            "https://www.booking.com/hotel/jp/foo.html "
            "和 https://www.agoda.com/zh-tw/bar-hotel/hotel/tokyo-jp.html "
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
    assert [item.platform for item in repository.items] == ["booking", "agoda"]
    assert repository.items[0].resolved_url == repository.items[0].url
    assert repository.items[1].resolved_url == repository.items[1].url
    assert all(item.group_id == "Cgroup123" for item in repository.items)
    assert fake_line_client.calls == [
        ("reply-token", "已收到 2 筆住宿連結，先幫你記下來了。")
    ]


def test_line_webhook_rejects_invalid_signature() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
    )
    client = TestClient(
        create_app(
            settings=settings,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    response = client.post(
        "/webhooks/line",
        json=payload,
        headers={"X-Line-Signature": "bad-signature"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid LINE signature."


def test_line_webhook_still_succeeds_when_reply_fails() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=FailingLineClient(),
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
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
    assert response.json() == {"ok": True, "captured": 1}
    assert repository.items[0].url == "https://www.booking.com/hotel/jp/foo.html"
    assert repository.items[0].resolved_url == "https://www.booking.com/hotel/jp/foo.html"


def test_line_webhook_ignores_non_lodging_agoda_links() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload(
        (
            "這兩個不要收 "
            "https://www.agoda.com/activities/detail?cid=1 "
            "https://www.agoda.com/travel-guides/japan/tokyo"
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
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == []


def test_line_webhook_ignores_non_lodging_booking_links() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload(
        "這個不要收 https://www.booking.com/searchresults.zh-tw.html?ss=Tokyo"
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
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == []


def test_line_webhook_resolves_agoda_short_links_before_capture() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    short_url = "https://www.agoda.com/sp/B70FF37xamn"
    resolved_url = (
        "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
        "?pid=redirect"
    )
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=FakeLineClient(),
            lodging_link_service=LodgingLinkService(resolver),
        )
    )

    payload = _build_payload(short_url)
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
    assert response.json() == {"ok": True, "captured": 1}
    assert repository.items[0].url == short_url
    assert repository.items[0].resolved_url == resolved_url
    assert resolver.calls == [short_url]


def test_line_webhook_resolves_booking_short_links_before_capture() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    short_url = "https://www.booking.com/Share-08PTGo"
    resolved_url = "https://www.booking.com/hotel/jp/hotel-resol-ueno.zh-tw.html"
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=FakeLineClient(),
            lodging_link_service=LodgingLinkService(resolver),
        )
    )

    payload = _build_payload(short_url)
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
    assert response.json() == {"ok": True, "captured": 1}
    assert repository.items[0].url == short_url
    assert repository.items[0].resolved_url == resolved_url
    assert resolver.calls == [short_url]
