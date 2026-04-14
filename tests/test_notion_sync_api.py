from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.notion_sync.models import (
    NotionDatabaseTarget,
    NotionPageResult,
    NotionSyncCandidate,
    NotionSyncDocument,
    NotionSyncSourceScope,
)
from app.notion_sync.targets import NotionTargetConfig

DEFAULT_TRIP_ID = "trip-current"
DEFAULT_TRIP_TITLE = "東京 2026"


class DummyCollector:
    def append_many(self, items) -> int:
        return len(items)


class InMemoryNotionSyncRepository:
    def __init__(self) -> None:
        self.documents: dict[str, NotionSyncDocument] = {
            "doc-pending": NotionSyncDocument(
                document_id="doc-pending",
                platform="booking",
                url="https://short.example/1",
                resolved_url="https://www.booking.com/hotel/jp/resol.html",
                property_name="Hotel Resol Ueno",
                city="Tokyo",
                country_code="JP",
                map_status="resolved",
                details_status="resolved",
                pricing_status="resolved",
                notion_sync_status="pending",
                captured_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
                source_type="group",
                group_id="group-123",
            ),
            "doc-synced": NotionSyncDocument(
                document_id="doc-synced",
                platform="agoda",
                url="https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
                resolved_url="https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
                property_name="Existing Hotel",
                city="Tokyo",
                country_code="JP",
                price_amount=22000,
                price_currency="JPY",
                notion_page_id="page-existing",
                notion_page_url="https://www.notion.so/page-existing",
                notion_database_id="db-existing",
                notion_data_source_id="ds-existing",
                notion_sync_status="synced",
                notion_last_synced_at=datetime(2026, 3, 26, tzinfo=timezone.utc),
                captured_at=datetime(2026, 3, 24, tzinfo=timezone.utc),
                source_type="group",
                group_id="group-999",
            ),
            "doc-failed": NotionSyncDocument(
                document_id="doc-failed",
                platform="booking",
                url="https://www.booking.com/hotel/jp/failed.html",
                resolved_url="https://www.booking.com/hotel/jp/failed.html",
                notion_sync_status="failed",
                notion_sync_error="simulated old failure",
                notion_sync_retry_count=2,
                captured_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
                source_type="group",
                group_id="group-123",
            ),
        }

    def find_pending(self, limit: int | None, source_scope=None):
        items = [
            self._to_candidate(item)
            for item in self.documents.values()
            if item.notion_sync_status != "synced"
            and _matches_source_scope(item, source_scope)
        ]
        items.sort(
            key=lambda item: item.captured_at
            or datetime.min.replace(tzinfo=timezone.utc)
        )
        if limit is None:
            return items
        return items[:limit]

    def find_all(self, limit: int | None = None, source_scope=None):
        items = [
            self._to_candidate(item)
            for item in self.documents.values()
            if _matches_source_scope(item, source_scope)
        ]
        items.sort(
            key=lambda item: item.captured_at
            or datetime.min.replace(tzinfo=timezone.utc)
        )
        if limit is None:
            return items
        return items[:limit]

    def find_by_document_id(self, document_id: str):
        document = self.documents.get(document_id)
        if document is None:
            return None
        return self._to_candidate(document)

    def list_documents(self, limit: int, statuses=None, source_scope=None):
        items = list(self.documents.values())
        if statuses:
            items = [item for item in items if item.notion_sync_status in statuses]
        if source_scope is not None:
            items = [item for item in items if _matches_source_scope(item, source_scope)]
        items.sort(
            key=lambda item: item.captured_at
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return items[:limit]

    def mark_synced(
        self,
        document_id: str,
        *,
        page_id: str,
        page_url: str | None,
        database_id: str | None,
        data_source_id: str | None,
    ) -> None:
        current = self.documents[document_id]
        self.documents[document_id] = NotionSyncDocument(
            document_id=current.document_id,
            platform=current.platform,
            url=current.url,
            resolved_url=current.resolved_url,
            property_name=current.property_name,
            formatted_address=current.formatted_address,
            city=current.city,
            country_code=current.country_code,
            property_type=current.property_type,
            amenities=current.amenities,
            price_amount=current.price_amount,
            price_currency=current.price_currency,
            is_sold_out=current.is_sold_out,
            google_maps_url=current.google_maps_url,
            google_maps_search_url=current.google_maps_search_url,
            map_status=current.map_status,
            details_status=current.details_status,
            pricing_status=current.pricing_status,
            notion_page_id=page_id,
            notion_page_url=page_url,
            notion_database_id=database_id,
            notion_data_source_id=data_source_id,
            notion_sync_status="synced",
            notion_sync_error=None,
            notion_sync_retry_count=0,
            notion_last_attempt_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
            notion_last_synced_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
            captured_at=current.captured_at,
            source_type=current.source_type,
            group_id=current.group_id,
            room_id=current.room_id,
            user_id=current.user_id,
            trip_id=current.trip_id,
            trip_title=current.trip_title,
        )

    def mark_failed(self, document_id: str, error: str) -> None:
        current = self.documents[document_id]
        self.documents[document_id] = NotionSyncDocument(
            document_id=current.document_id,
            platform=current.platform,
            url=current.url,
            resolved_url=current.resolved_url,
            property_name=current.property_name,
            formatted_address=current.formatted_address,
            city=current.city,
            country_code=current.country_code,
            property_type=current.property_type,
            amenities=current.amenities,
            price_amount=current.price_amount,
            price_currency=current.price_currency,
            is_sold_out=current.is_sold_out,
            google_maps_url=current.google_maps_url,
            google_maps_search_url=current.google_maps_search_url,
            map_status=current.map_status,
            details_status=current.details_status,
            pricing_status=current.pricing_status,
            notion_page_id=current.notion_page_id,
            notion_page_url=current.notion_page_url,
            notion_database_id=current.notion_database_id,
            notion_data_source_id=current.notion_data_source_id,
            notion_sync_status="failed",
            notion_sync_error=error,
            notion_sync_retry_count=current.notion_sync_retry_count + 1,
            notion_last_attempt_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
            notion_last_synced_at=current.notion_last_synced_at,
            captured_at=current.captured_at,
            source_type=current.source_type,
            group_id=current.group_id,
            room_id=current.room_id,
            user_id=current.user_id,
            trip_id=current.trip_id,
            trip_title=current.trip_title,
        )

    def _to_candidate(self, item: NotionSyncDocument) -> NotionSyncCandidate:
        return NotionSyncCandidate(
            document_id=item.document_id,
            platform=item.platform,
            url=item.url,
            resolved_url=item.resolved_url,
            property_name=item.property_name,
            formatted_address=item.formatted_address,
            city=item.city,
            country_code=item.country_code,
            property_type=item.property_type,
            amenities=item.amenities,
            price_amount=item.price_amount,
            price_currency=item.price_currency,
            is_sold_out=item.is_sold_out,
            google_maps_url=item.google_maps_url,
            google_maps_search_url=item.google_maps_search_url,
            map_status=item.map_status,
            details_status=item.details_status,
            pricing_status=item.pricing_status,
            captured_at=item.captured_at,
            notion_page_id=item.notion_page_id,
            notion_database_id=item.notion_database_id,
            notion_data_source_id=item.notion_data_source_id,
            source_type=item.source_type,
            group_id=item.group_id,
            room_id=item.room_id,
            user_id=item.user_id,
            trip_id=item.trip_id,
            trip_title=item.trip_title,
        )


class FakeNotionSyncService:
    def __init__(
        self,
        *,
        parent_page_id: str = "page-parent",
        database_id: str = "",
        data_source_id: str = "",
        database_title: str = "Nihon LINE Bot Lodgings",
        database_url: str = "",
        public_database_url: str = "",
    ) -> None:
        self.parent_page_id = parent_page_id
        self.database_id = database_id
        self.data_source_id = data_source_id
        self.database_title = database_title
        self.database_url = database_url
        self.public_database_url = public_database_url
        self.calls: list[str] = []
        self.failing_document_ids: set[str] = set()

    @property
    def is_setup_configured(self) -> bool:
        return bool(self.parent_page_id or self.data_source_id)

    @property
    def is_sync_configured(self) -> bool:
        return bool(self.data_source_id)

    async def setup_database(self, title: str | None = None) -> NotionDatabaseTarget:
        if not self.data_source_id:
            self.data_source_id = "ds-456"
        if not self.database_id:
            suffix = self.data_source_id.removeprefix("ds-")
            self.database_id = f"db-{suffix}"
        self.database_url = (
            f"https://www.notion.so/workspace/{self.database_id}?v=view-{self.data_source_id}"
        )
        self.public_database_url = f"https://www.notion.so/public-{self.database_id}"
        if title:
            self.database_title = title
        return NotionDatabaseTarget(
            database_id=self.database_id,
            data_source_id=self.data_source_id,
            title=self.database_title,
            url=self.database_url,
            public_url=self.public_database_url,
        )

    def clone_with_target(
        self,
        *,
        parent_page_id: str = "",
        database_id: str = "",
        data_source_id: str = "",
        database_title: str = "Nihon LINE Bot Lodgings",
        database_url: str = "",
        public_database_url: str = "",
    ) -> "FakeNotionSyncService":
        clone = FakeNotionSyncService(
            parent_page_id=parent_page_id,
            database_id=database_id,
            data_source_id=data_source_id,
            database_title=database_title,
            database_url=database_url,
            public_database_url=public_database_url,
        )
        clone.calls = self.calls
        clone.failing_document_ids = self.failing_document_ids
        return clone

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult:
        document_id = str(candidate.document_id)
        self.calls.append(document_id)
        if document_id in self.failing_document_ids:
            raise RuntimeError("simulated sync failure")
        if (
            candidate.notion_page_id
            and candidate.notion_data_source_id == self.data_source_id
        ):
            return NotionPageResult(
                page_id=candidate.notion_page_id,
                page_url=f"https://www.notion.so/{candidate.notion_page_id}",
                created=False,
            )
        return NotionPageResult(
            page_id=f"page-{document_id}",
            page_url=f"https://www.notion.so/page-{document_id}",
            created=True,
        )


class InMemoryNotionTargetRepository:
    def __init__(self) -> None:
        self.targets: dict[tuple[str, str, str | None], NotionTargetConfig] = {}

    def find_by_source_scope(
        self,
        source_scope: NotionSyncSourceScope,
    ) -> NotionTargetConfig | None:
        return self.targets.get(_scope_key(source_scope))

    def save(self, target: NotionTargetConfig) -> None:
        source_scope = target.source_scope
        assert source_scope is not None
        self.targets[_scope_key(source_scope)] = target


def test_notion_setup_endpoint_creates_database_and_updates_settings() -> None:
    settings = Settings(
        notion_api_token="secret",
        notion_parent_page_id="page-parent",
    )
    repository = InMemoryNotionSyncRepository()
    service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
        )
    )

    response = client.post("/jobs/notion-sync/setup", json={"title": "Trip Lodgings"})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Notion database is ready for lodging sync."
    assert body["data"]["database_id"] == "db-456"
    assert body["data"]["data_source_id"] == "ds-456"
    assert body["data"]["database_title"] == "Trip Lodgings"
    assert body["data"]["database_url"] == "https://www.notion.so/workspace/db-456?v=view-ds-456"
    assert body["data"]["database_public_url"] == "https://www.notion.so/public-db-456"
    assert settings.notion_database_id == "db-456"
    assert settings.notion_data_source_id == "ds-456"
    assert settings.notion_database_url == "https://www.notion.so/workspace/db-456?v=view-ds-456"
    assert settings.notion_public_database_url == "https://www.notion.so/public-db-456"


def test_notion_sync_documents_endpoint_lists_repository_state() -> None:
    settings = Settings()
    repository = InMemoryNotionSyncRepository()
    service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
        )
    )

    response = client.get("/jobs/notion-sync/documents", params={"limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Fetched Notion sync documents."
    assert body["data"]["documents"][0]["document_id"] == "doc-pending"
    assert body["data"]["documents"][0]["notion_sync_status"] == "pending"
    assert body["data"]["documents"][0]["group_id"] == "group-123"
    assert body["data"]["documents"][1]["document_id"] == "doc-synced"
    assert body["data"]["documents"][1]["notion_page_id"] == "page-existing"


def test_notion_sync_run_endpoint_processes_pending_documents() -> None:
    settings = Settings(
        notion_api_token="secret",
        notion_parent_page_id="page-parent",
        notion_data_source_id="ds-456",
        notion_sync_batch_size=10,
    )
    repository = InMemoryNotionSyncRepository()
    service = FakeNotionSyncService()
    service.data_source_id = "ds-456"
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
        )
    )

    response = client.post("/jobs/notion-sync/run")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Notion sync job finished."
    assert body["data"]["processed"] == 2
    assert body["data"]["created"] == 2
    assert body["data"]["updated"] == 0
    assert body["data"]["failed"] == 0
    assert body["data"]["target_source"] == "default"
    assert repository.documents["doc-pending"].notion_sync_status == "synced"
    assert repository.documents["doc-failed"].notion_sync_status == "synced"
    assert repository.documents["doc-pending"].notion_data_source_id == "ds-456"


def test_notion_sync_retry_endpoint_marks_failure() -> None:
    settings = Settings(
        notion_api_token="secret",
        notion_parent_page_id="page-parent",
        notion_data_source_id="ds-456",
    )
    repository = InMemoryNotionSyncRepository()
    service = FakeNotionSyncService()
    service.data_source_id = "ds-456"
    service.failing_document_ids = {"doc-failed"}
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
        )
    )

    response = client.post("/jobs/notion-sync/documents/doc-failed/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Notion sync retry finished."
    assert body["data"]["failed"] == 1
    assert repository.documents["doc-failed"].notion_sync_status == "failed"
    assert repository.documents["doc-failed"].notion_sync_retry_count == 3


def test_notion_setup_endpoint_can_store_scoped_target() -> None:
    settings = Settings(
        notion_api_token="secret",
        notion_parent_page_id="page-parent",
    )
    repository = InMemoryNotionSyncRepository()
    target_repository = InMemoryNotionTargetRepository()
    service = FakeNotionSyncService(parent_page_id="")
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
            notion_target_repository=target_repository,
        )
    )

    response = client.post(
        "/jobs/notion-sync/setup",
        json={
            "title": "Group Trip",
            "source_type": "group",
            "group_id": "group-123",
            "parent_page_id": "page-group-123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["target_source"] == "scoped"
    assert body["data"]["group_id"] == "group-123"
    assert settings.notion_database_id == ""
    stored_target = target_repository.find_by_source_scope(
        NotionSyncSourceScope(source_type="group", group_id="group-123")
    )
    assert stored_target is not None
    assert stored_target.parent_page_id == "page-group-123"
    assert stored_target.data_source_id == "ds-456"


def test_notion_setup_endpoint_can_store_trip_scoped_target() -> None:
    settings = Settings(
        notion_api_token="secret",
        notion_parent_page_id="page-parent",
    )
    repository = InMemoryNotionSyncRepository()
    target_repository = InMemoryNotionTargetRepository()
    service = FakeNotionSyncService(parent_page_id="")
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
            notion_target_repository=target_repository,
        )
    )

    response = client.post(
        "/jobs/notion-sync/setup",
        json={
            "title": DEFAULT_TRIP_TITLE,
            "source_type": "group",
            "group_id": "group-123",
            "trip_id": DEFAULT_TRIP_ID,
            "trip_title": DEFAULT_TRIP_TITLE,
            "parent_page_id": "page-trip-123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["target_source"] == "scoped"
    assert body["data"]["trip_id"] == DEFAULT_TRIP_ID
    assert body["data"]["trip_title"] == DEFAULT_TRIP_TITLE
    stored_target = target_repository.find_by_source_scope(_trip_scope())
    assert stored_target is not None
    assert stored_target.parent_page_id == "page-trip-123"
    assert stored_target.data_source_id == "ds-456"


def test_notion_sync_run_endpoint_can_use_scoped_target() -> None:
    settings = Settings(
        notion_api_token="secret",
        notion_sync_batch_size=10,
    )
    repository = InMemoryNotionSyncRepository()
    target_repository = InMemoryNotionTargetRepository()
    target_repository.save(
        NotionTargetConfig.from_source_scope(
            NotionSyncSourceScope(source_type="group", group_id="group-123"),
            parent_page_id="page-group-123",
            database_id="db-group-123",
            data_source_id="ds-group-123",
            database_title="Group Trip",
            database_url="https://www.notion.so/workspace/db-group-123?v=view-group-123",
            public_database_url="https://www.notion.so/public-db-group-123",
        )
    )
    service = FakeNotionSyncService(parent_page_id="")
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
            notion_target_repository=target_repository,
        )
    )

    response = client.post(
        "/jobs/notion-sync/run",
        json={"source_type": "group", "group_id": "group-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["target_source"] == "scoped"
    assert body["data"]["group_id"] == "group-123"
    assert repository.documents["doc-pending"].notion_data_source_id == "ds-group-123"
    assert repository.documents["doc-failed"].notion_data_source_id == "ds-group-123"


def test_notion_sync_run_endpoint_can_use_trip_scoped_target() -> None:
    settings = Settings(
        notion_api_token="secret",
        notion_sync_batch_size=10,
    )
    repository = InMemoryNotionSyncRepository()
    repository.documents["doc-pending"] = replace(
        repository.documents["doc-pending"],
        trip_id=DEFAULT_TRIP_ID,
        trip_title=DEFAULT_TRIP_TITLE,
    )
    repository.documents["doc-failed"] = replace(
        repository.documents["doc-failed"],
        trip_id=DEFAULT_TRIP_ID,
        trip_title=DEFAULT_TRIP_TITLE,
    )
    target_repository = InMemoryNotionTargetRepository()
    target_repository.save(
        NotionTargetConfig.from_source_scope(
            _trip_scope(),
            parent_page_id="page-trip-123",
            database_id="db-trip-123",
            data_source_id="ds-trip-123",
            database_title=DEFAULT_TRIP_TITLE,
            database_url="https://www.notion.so/workspace/db-trip-123?v=view-trip-123",
            public_database_url="https://www.notion.so/public-db-trip-123",
        )
    )
    service = FakeNotionSyncService(parent_page_id="")
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
            notion_target_repository=target_repository,
        )
    )

    response = client.post(
        "/jobs/notion-sync/run",
        json={
            "source_type": "group",
            "group_id": "group-123",
            "trip_id": DEFAULT_TRIP_ID,
            "trip_title": DEFAULT_TRIP_TITLE,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["target_source"] == "scoped"
    assert body["data"]["trip_id"] == DEFAULT_TRIP_ID
    assert repository.documents["doc-pending"].notion_data_source_id == "ds-trip-123"
    assert repository.documents["doc-failed"].notion_data_source_id == "ds-trip-123"


def test_notion_sync_documents_endpoint_can_filter_by_scope() -> None:
    settings = Settings()
    repository = InMemoryNotionSyncRepository()
    service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=DummyCollector(),
            notion_sync_repository=repository,
            notion_sync_service=service,
        )
    )

    response = client.get(
        "/jobs/notion-sync/documents",
        params={"limit": 10, "source_type": "group", "group_id": "group-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["document_id"] for item in body["data"]["documents"]] == [
        "doc-pending",
        "doc-failed",
    ]


def _matches_source_scope(
    item: NotionSyncDocument,
    source_scope: NotionSyncSourceScope | None,
) -> bool:
    if source_scope is None:
        return True
    if item.source_type != source_scope.source_type:
        return False
    if source_scope.trip_id is not None and item.trip_id != source_scope.trip_id:
        return False
    if source_scope.source_type == "group":
        return item.group_id == source_scope.group_id
    if source_scope.source_type == "room":
        return item.room_id == source_scope.room_id
    if source_scope.source_type == "user":
        return item.user_id == source_scope.user_id
    return False


def _scope_key(source_scope: NotionSyncSourceScope) -> tuple[str, str, str | None]:
    if source_scope.source_type == "group":
        return ("group", str(source_scope.group_id), source_scope.trip_id)
    if source_scope.source_type == "room":
        return ("room", str(source_scope.room_id), source_scope.trip_id)
    return ("user", str(source_scope.user_id), source_scope.trip_id)


def _trip_scope() -> NotionSyncSourceScope:
    return NotionSyncSourceScope(
        source_type="group",
        group_id="group-123",
        trip_id=DEFAULT_TRIP_ID,
        trip_title=DEFAULT_TRIP_TITLE,
    )
