from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Sequence

from app.notion_sync.job import run_notion_sync_job
from app.notion_sync.models import NotionPageResult, NotionSyncCandidate


class InMemoryNotionSyncRepository:
    def __init__(self, items: Sequence[NotionSyncCandidate]) -> None:
        self.items = list(items)
        self.synced: dict[str, tuple[str, str | None]] = {}
        self.failed: dict[str, str] = {}

    def find_pending(self, limit: int) -> Sequence[NotionSyncCandidate]:
        return self.items[:limit]

    def find_all(self, limit: int | None = None) -> Sequence[NotionSyncCandidate]:
        if limit is None:
            return self.items
        return self.items[:limit]

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
    ) -> None:
        self.synced[document_id] = (page_id, page_url)

    def mark_failed(self, document_id: str, error: str) -> None:
        self.failed[document_id] = error


class FakeNotionSyncService:
    def __init__(
        self,
        results: dict[str, NotionPageResult],
        failing_document_ids: set[str] | None = None,
    ) -> None:
        self.results = results
        self.failing_document_ids = failing_document_ids or set()
        self.calls: list[str] = []

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult:
        document_id = str(candidate.document_id)
        self.calls.append(document_id)
        if document_id in self.failing_document_ids:
            raise RuntimeError("simulated notion sync failure")
        return self.results[document_id]


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
    )
    assert repository.synced["doc-update"] == (
        "page-existing",
        "https://www.notion.so/page-existing",
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
