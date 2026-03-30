from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Sequence

from app.notion_sync.job import run_notion_sync_job
from app.notion_sync.models import (
    NotionPageResult,
    NotionSyncCandidate,
    NotionSyncSourceScope,
)


class InMemoryNotionSyncRepository:
    def __init__(self, items: Sequence[NotionSyncCandidate]) -> None:
        self.items = list(items)
        self.synced: dict[str, tuple[str, str | None, str | None, str | None]] = {}
        self.failed: dict[str, str] = {}
        self.pending_source_scopes: list[NotionSyncSourceScope | None] = []
        self.all_source_scopes: list[NotionSyncSourceScope | None] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncCandidate]:
        self.pending_source_scopes.append(source_scope)
        return _filter_candidates(self.items, limit=limit, source_scope=source_scope)

    def find_all(
        self,
        limit: int | None = None,
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncCandidate]:
        self.all_source_scopes.append(source_scope)
        return _filter_candidates(self.items, limit=limit, source_scope=source_scope)

    def find_by_document_id(self, document_id: str) -> NotionSyncCandidate | None:
        for item in self.items:
            if str(item.document_id) == document_id:
                return item
        return None

    def list_documents(self, limit: int, statuses=None):
        raise NotImplementedError

    def mark_synced(
        self,
        document_id: str,
        *,
        page_id: str,
        page_url: str | None,
        database_id: str | None,
        data_source_id: str | None,
    ) -> None:
        self.synced[document_id] = (
            page_id,
            page_url,
            database_id,
            data_source_id,
        )

    def mark_failed(self, document_id: str, error: str) -> None:
        self.failed[document_id] = error


class FakeNotionSyncService:
    def __init__(
        self,
        results: dict[str, NotionPageResult],
        failing_document_ids: set[str] | None = None,
    ) -> None:
        self.database_id = "db-current"
        self.data_source_id = "ds-current"
        self.results = results
        self.failing_document_ids = failing_document_ids or set()
        self.calls: list[str] = []

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult:
        document_id = str(candidate.document_id)
        self.calls.append(document_id)
        if document_id in self.failing_document_ids:
            raise RuntimeError("simulated notion sync failure")
        return self.results[document_id]


def _filter_candidates(
    items: Sequence[NotionSyncCandidate],
    *,
    limit: int | None,
    source_scope: NotionSyncSourceScope | None,
) -> Sequence[NotionSyncCandidate]:
    filtered = [
        item for item in items if _matches_source_scope(item, source_scope)
    ]
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


def test_run_notion_sync_job_creates_updates_and_marks_failures() -> None:
    repository = InMemoryNotionSyncRepository(
        [
            NotionSyncCandidate(
                document_id="doc-create",
                platform="booking",
                url="https://www.booking.com/hotel/jp/resol.html",
                property_name="Hotel Resol Ueno",
                city="Tokyo",
                country_code="JP",
                captured_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            ),
            NotionSyncCandidate(
                document_id="doc-update",
                platform="agoda",
                url="https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
                property_name="Existing Hotel",
                city="Tokyo",
                country_code="JP",
                captured_at=datetime(2026, 3, 26, tzinfo=timezone.utc),
                notion_page_id="page-existing",
            ),
            NotionSyncCandidate(
                document_id="doc-fail",
                platform="booking",
                url="https://www.booking.com/hotel/jp/fail.html",
                captured_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
            ),
        ]
    )
    service = FakeNotionSyncService(
        results={
            "doc-create": NotionPageResult(
                page_id="page-create",
                page_url="https://www.notion.so/page-create",
                created=True,
            ),
            "doc-update": NotionPageResult(
                page_id="page-existing",
                page_url="https://www.notion.so/page-existing",
                created=False,
            ),
        },
        failing_document_ids={"doc-fail"},
    )

    summary = asyncio.run(
        run_notion_sync_job(
            repository=repository,
            service=service,
            limit=10,
        )
    )

    assert summary.processed == 3
    assert summary.created == 1
    assert summary.updated == 1
    assert summary.failed == 1
    assert repository.synced["doc-create"] == (
        "page-create",
        "https://www.notion.so/page-create",
        "db-current",
        "ds-current",
    )
    assert repository.synced["doc-update"] == (
        "page-existing",
        "https://www.notion.so/page-existing",
        "db-current",
        "ds-current",
    )
    assert repository.failed["doc-fail"] == "simulated notion sync failure"
    assert service.calls == ["doc-create", "doc-update", "doc-fail"]


def test_run_notion_sync_job_can_force_sync_all_documents() -> None:
    repository = InMemoryNotionSyncRepository(
        [
            NotionSyncCandidate(
                document_id="doc-1",
                platform="booking",
                url="https://www.booking.com/hotel/jp/1.html",
                notion_page_id="page-1",
                captured_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            ),
            NotionSyncCandidate(
                document_id="doc-2",
                platform="agoda",
                url="https://www.agoda.com/zh-tw/foo/hotel/2.html",
                captured_at=datetime(2026, 3, 26, tzinfo=timezone.utc),
            ),
        ]
    )
    service = FakeNotionSyncService(
        results={
            "doc-1": NotionPageResult(page_id="page-1", created=False),
            "doc-2": NotionPageResult(page_id="page-2", created=True),
        }
    )

    summary = asyncio.run(
        run_notion_sync_job(
            repository=repository,
            service=service,
            limit=10,
            force=True,
        )
    )

    assert summary.processed == 2
    assert summary.created == 1
    assert summary.updated == 1
    assert summary.failed == 0


def test_run_notion_sync_job_can_filter_by_line_source_scope() -> None:
    repository = InMemoryNotionSyncRepository(
        [
            NotionSyncCandidate(
                document_id="doc-group-a",
                platform="booking",
                url="https://www.booking.com/hotel/jp/a.html",
                source_type="group",
                group_id="group-a",
                captured_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            ),
            NotionSyncCandidate(
                document_id="doc-group-b",
                platform="booking",
                url="https://www.booking.com/hotel/jp/b.html",
                source_type="group",
                group_id="group-b",
                captured_at=datetime(2026, 3, 26, tzinfo=timezone.utc),
            ),
            NotionSyncCandidate(
                document_id="doc-room-a",
                platform="agoda",
                url="https://www.agoda.com/zh-tw/foo/hotel/c.html",
                source_type="room",
                room_id="room-a",
                captured_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
            ),
        ]
    )
    service = FakeNotionSyncService(
        results={
            "doc-group-a": NotionPageResult(page_id="page-group-a", created=True),
        }
    )

    summary = asyncio.run(
        run_notion_sync_job(
            repository=repository,
            service=service,
            limit=None,
            source_scope=NotionSyncSourceScope(
                source_type="group",
                group_id="group-a",
            ),
        )
    )

    assert summary.processed == 1
    assert summary.created == 1
    assert summary.updated == 0
    assert summary.failed == 0
    assert repository.pending_source_scopes == [
        NotionSyncSourceScope(source_type="group", group_id="group-a")
    ]
    assert service.calls == ["doc-group-a"]
