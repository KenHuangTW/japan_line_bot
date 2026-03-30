from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.config import Settings
from app.lodging_links.common import build_lodging_lookup_keys
from app.lodging_links.service import LodgingLinkService
from app.line_security import generate_signature
from app.main import create_app
from app.models import CapturedLodgingLink
from app.notion_sync.models import (
    NotionPageResult,
    NotionSyncCandidate,
    NotionSyncSourceScope,
)


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

    def find_duplicate(
        self,
        urls: Sequence[str],
        *,
        source_type: str,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
    ) -> CapturedLodgingLink | None:
        candidate_keys = set(build_lodging_lookup_keys(*urls))
        if not candidate_keys:
            return None

        matches = [
            item
            for item in self.items
            if _matches_captured_source(
                item,
                source_type=source_type,
                group_id=group_id,
                room_id=room_id,
                user_id=user_id,
            )
            and candidate_keys.intersection(
                build_lodging_lookup_keys(item.url, item.resolved_url)
            )
        ]
        if not matches:
            return None

        return min(matches, key=lambda item: (len(item.url), -item.captured_at.timestamp()))


class InMemoryNotionSyncRepository:
    def __init__(
        self,
        *,
        pending_items: Sequence[NotionSyncCandidate] | None = None,
        all_items: Sequence[NotionSyncCandidate] | None = None,
    ) -> None:
        self.pending_items = list(pending_items or [])
        self.all_items = list(all_items or self.pending_items)
        self.pending_limits: list[int | None] = []
        self.all_limits: list[int | None] = []
        self.pending_source_scopes: list[NotionSyncSourceScope | None] = []
        self.all_source_scopes: list[NotionSyncSourceScope | None] = []
        self.synced: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
    ):
        self.pending_limits.append(limit)
        self.pending_source_scopes.append(source_scope)
        return _filter_notion_candidates(
            self.pending_items,
            limit=limit,
            source_scope=source_scope,
        )

    def find_all(
        self,
        limit: int | None = None,
        source_scope: NotionSyncSourceScope | None = None,
    ):
        self.all_limits.append(limit)
        self.all_source_scopes.append(source_scope)
        return _filter_notion_candidates(
            self.all_items,
            limit=limit,
            source_scope=source_scope,
        )

    def find_by_document_id(self, document_id: str):
        for item in self.all_items:
            if str(item.document_id) == document_id:
                return item
        return None

    def list_documents(self, limit: int, statuses=None):
        raise NotImplementedError

    def mark_synced(
        self,
        document_id,
        *,
        page_id: str,
        page_url: str | None,
        database_id: str | None,
        data_source_id: str | None,
    ) -> None:
        self.synced.append(str(document_id))

    def mark_failed(self, document_id, error: str) -> None:
        self.failed.append((str(document_id), error))


class FakeNotionSyncService:
    def __init__(self, *, is_sync_configured: bool = True) -> None:
        self.database_id = "db-current" if is_sync_configured else ""
        self.data_source_id = "ds-current" if is_sync_configured else ""
        self.calls: list[str] = []
        self.setup_calls: list[str | None] = []

    @property
    def is_sync_configured(self) -> bool:
        return bool(self.data_source_id)

    async def setup_database(self, title: str | None = None):
        self.setup_calls.append(title)
        return None

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult:
        document_id = str(candidate.document_id)
        self.calls.append(document_id)
        return NotionPageResult(
            page_id=f"page-{document_id}",
            page_url=f"https://www.notion.so/page-{document_id}",
            created=not (
                candidate.notion_page_id
                and candidate.notion_data_source_id == self.data_source_id
            ),
        )


def _build_payload(
    message_text: str,
    *,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
) -> dict[str, object]:
    return {
        "destination": "Ubot",
        "events": [
            {
                "type": "message",
                "replyToken": "reply-token",
                "mode": "active",
                "timestamp": 1711111111111,
                "source": {
                    "type": source_type,
                    "groupId": group_id,
                    "roomId": room_id,
                    "userId": user_id,
                },
                "message": {
                    "id": "325708",
                    "type": "text",
                    "text": message_text,
                },
            }
        ],
    }


def _build_notion_candidate(
    document_id: str,
    *,
    notion_page_id: str | None = None,
    notion_data_source_id: str | None = None,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
) -> NotionSyncCandidate:
    return NotionSyncCandidate(
        document_id=document_id,
        platform="booking",
        url=f"https://www.booking.com/hotel/jp/{document_id}.html",
        captured_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source_type=source_type,
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        notion_page_id=notion_page_id,
        notion_data_source_id=notion_data_source_id,
    )


def _filter_notion_candidates(
    items: Sequence[NotionSyncCandidate],
    *,
    limit: int | None,
    source_scope: NotionSyncSourceScope | None,
) -> list[NotionSyncCandidate]:
    filtered = [item for item in items if _matches_source_scope(item, source_scope)]
    if limit is None:
        return filtered
    return filtered[:limit]


def _matches_source_scope(
    item: NotionSyncCandidate,
    source_scope: NotionSyncSourceScope | None,
) -> bool:
    if source_scope is None:
        return True
    if item.source_type != source_scope.source_type:
        return False
    if source_scope.source_type == "group":
        return item.group_id == source_scope.group_id
    if source_scope.source_type == "room":
        return item.room_id == source_scope.room_id
    if source_scope.source_type == "user":
        return item.user_id == source_scope.user_id
    return False


def _build_captured_link(
    url: str,
    *,
    resolved_url: str | None = None,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
    captured_at: datetime | None = None,
) -> CapturedLodgingLink:
    hostname = (urlsplit(url).hostname or "").lower()
    return CapturedLodgingLink(
        platform="agoda" if "agoda.com" in hostname else "booking",
        url=url,
        hostname=hostname,
        resolved_url=resolved_url or url,
        resolved_hostname=(urlsplit(resolved_url or url).hostname or "").lower(),
        message_text=f"請看 {url}",
        source_type=source_type,
        destination="Ubot",
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        message_id="325708",
        event_timestamp_ms=1711111111111,
        event_mode="active",
        captured_at=captured_at or datetime(2026, 3, 30, tzinfo=timezone.utc),
    )


def _matches_captured_source(
    item: CapturedLodgingLink,
    *,
    source_type: str,
    group_id: str | None,
    room_id: str | None,
    user_id: str | None,
) -> bool:
    if item.source_type != source_type:
        return False
    if source_type == "group":
        return item.group_id == group_id
    if source_type == "room":
        return item.room_id == room_id
    if source_type == "user":
        return item.user_id == user_id
    return True


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
    assert all(item.map_status == "pending" for item in repository.items)
    assert all(item.map_retry_count == 0 for item in repository.items)
    assert all(item.google_maps_url is None for item in repository.items)
    assert all(item.group_id == "Cgroup123" for item in repository.items)
    assert fake_line_client.calls == [
        ("reply-token", "已收到 2 筆住宿連結，先幫你記下來了。")
    ]


def test_line_webhook_replies_pong_for_ping_command() -> None:
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

    payload = _build_payload("/ping")
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
    assert fake_line_client.calls == [("reply-token", "pong")]


def test_line_webhook_runs_pending_notion_sync_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_repository = InMemoryNotionSyncRepository(
        pending_items=[
            _build_notion_candidate("doc-1"),
            _build_notion_candidate("doc-2"),
            _build_notion_candidate("doc-other-group", group_id="Cgroup999"),
        ]
    )
    notion_service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
        )
    )

    payload = _build_payload("/整理", source_type="group", group_id="Cgroup123")
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
    assert notion_repository.pending_limits == [None]
    assert notion_repository.all_limits == []
    assert notion_repository.pending_source_scopes == [
        NotionSyncSourceScope(source_type="group", group_id="Cgroup123")
    ]
    assert notion_service.calls == ["doc-1", "doc-2"]
    assert fake_line_client.calls == [
        ("reply-token", "Notion 整理完成：處理 2 筆，新增 2 筆，更新 0 筆，失敗 0 筆。")
    ]


def test_line_webhook_runs_force_notion_sync_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_repository = InMemoryNotionSyncRepository(
        all_items=[
            _build_notion_candidate(
                "doc-1",
                notion_page_id="page-doc-1",
                notion_data_source_id="ds-current",
                source_type="room",
                group_id=None,
                room_id="Rroom123",
            ),
            _build_notion_candidate(
                "doc-2",
                source_type="room",
                group_id=None,
                room_id="Rroom123",
            ),
            _build_notion_candidate(
                "doc-other-room",
                source_type="room",
                group_id=None,
                room_id="Rroom999",
            ),
        ]
    )
    notion_service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
        )
    )

    payload = _build_payload(
        "/全部重來",
        source_type="room",
        group_id=None,
        room_id="Rroom123",
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
    assert notion_repository.pending_limits == []
    assert notion_repository.all_limits == [None]
    assert notion_repository.all_source_scopes == [
        NotionSyncSourceScope(source_type="room", room_id="Rroom123")
    ]
    assert notion_service.setup_calls == [None]
    assert notion_service.calls == ["doc-1", "doc-2"]
    assert fake_line_client.calls == [
        ("reply-token", "Notion 全部重來完成：處理 2 筆，新增 1 筆，更新 1 筆，失敗 0 筆。")
    ]


def test_line_webhook_reports_when_notion_sync_is_not_configured() -> None:
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

    payload = _build_payload("/整理")
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
    assert fake_line_client.calls == [("reply-token", "Notion sync 尚未設定完成。")]


def test_line_webhook_reports_when_chat_source_cannot_be_identified() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_repository = InMemoryNotionSyncRepository(
        pending_items=[_build_notion_candidate("doc-1")]
    )
    notion_service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
        )
    )

    payload = _build_payload("/整理", source_type="group", group_id=None)
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
    assert notion_repository.pending_limits == []
    assert notion_service.calls == []
    assert fake_line_client.calls == [
        ("reply-token", "無法辨識目前聊天室，暫時無法執行 Notion sync。")
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


def test_line_webhook_replies_saved_short_link_for_duplicate_direct_url() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.extend(
        [
            _build_captured_link(
                "https://www.booking.com/Share-older",
                resolved_url="https://www.booking.com/hotel/jp/foo.html",
                captured_at=datetime(2026, 3, 29, tzinfo=timezone.utc),
            ),
            _build_captured_link(
                "https://www.booking.com/hotel/jp/foo.html",
                captured_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
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
    assert response.json() == {"ok": True, "captured": 0}
    assert len(repository.items) == 2
    assert fake_line_client.calls == [
        ("reply-token", "你是不是在找這個\nhttps://www.booking.com/Share-older")
    ]


def test_line_webhook_replies_current_short_link_for_duplicate_resolved_url() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    short_url = "https://www.booking.com/Share-08PTGo"
    resolved_url = "https://www.booking.com/hotel/jp/foo.html"
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(_build_captured_link(resolved_url))
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
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
    assert response.json() == {"ok": True, "captured": 0}
    assert len(repository.items) == 1
    assert resolver.calls == [short_url]
    assert fake_line_client.calls == [
        ("reply-token", f"你是不是在找這個\n{short_url}")
    ]


def test_line_webhook_matches_duplicates_when_saved_resolved_url_has_tracking_query() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link(
            "https://www.agoda.com/sp/B70FF37xamn",
            resolved_url=(
                "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
                "?pid=redirect"
            ),
        )
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload(
        "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
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
    assert len(repository.items) == 1
    assert fake_line_client.calls == [
        ("reply-token", "你是不是在找這個\nhttps://www.agoda.com/sp/B70FF37xamn")
    ]


def test_line_webhook_only_checks_duplicates_within_same_chat() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
            group_id="Cother-group",
        )
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
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
    assert len(repository.items) == 2
    assert fake_line_client.calls == [
        ("reply-token", "已收到 1 筆住宿連結，先幫你記下來了。")
    ]
