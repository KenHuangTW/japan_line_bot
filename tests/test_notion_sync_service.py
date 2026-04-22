from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.notion_sync.job import _build_candidate
from app.notion_sync.models import NotionDatabaseTarget, NotionPageResult, NotionSyncCandidate
from app.notion_sync.service import (
    AMENITIES_PROPERTY,
    DECISION_STATUS_PROPERTY,
    DOCUMENT_ID_PROPERTY,
    GOOGLE_MAPS_PROPERTY,
    LAST_UPDATED_PROPERTY,
    LODGING_URL_PROPERTY,
    NotionApiError,
    NotionLodgingSyncService,
    PLATFORM_PROPERTY,
    TITLE_PROPERTY,
    build_notion_data_source_properties,
    build_notion_data_source_update_properties,
    build_notion_page_properties,
)


class FakeNotionClient:
    def __init__(self) -> None:
        self.created_databases: list[tuple[str, str]] = []
        self.retrieved_databases: list[str] = []
        self.updated_data_sources: list[tuple[str, str, dict[str, object]]] = []
        self.retrieved_pages: dict[str, dict[str, object]] = {}
        self.created_pages: list[tuple[str, dict[str, object]]] = []
        self.updated_pages: list[tuple[str, dict[str, object]]] = []
        self.update_page_errors: dict[str, NotionApiError] = {}

    async def create_database(
        self,
        *,
        parent_page_id: str,
        title: str,
    ) -> NotionDatabaseTarget:
        self.created_databases.append((parent_page_id, title))
        return NotionDatabaseTarget(
            database_id="db-created",
            data_source_id="ds-created",
            title=title,
            url="https://www.notion.so/workspace/db-created?v=view-created",
            public_url="https://www.notion.so/public-db-created",
        )

    async def retrieve_database(
        self,
        *,
        database_id: str,
    ) -> dict[str, object]:
        self.retrieved_databases.append(database_id)
        return {
            "id": database_id,
            "title": [{"type": "text", "text": {"content": "住宿清單"}}],
            "url": f"https://www.notion.so/workspace/{database_id}?v=view-shared",
            "public_url": f"https://www.notion.so/public-{database_id}",
            "data_sources": [{"id": "ds-existing"}],
        }

    async def retrieve_data_source(
        self,
        *,
        data_source_id: str,
    ) -> dict[str, object]:
        return {
            "id": data_source_id,
            "title": [{"type": "text", "text": {"content": "舊標題"}}],
            "parent": {"database_id": "db-existing"},
            "properties": {
                "Name": {"id": "title", "type": "title"},
                "Platform": {"id": "platform-id", "type": "select"},
                "Captured At": {"id": "captured-id", "type": "date"},
                "City": {"id": "city-id", "type": "rich_text"},
            },
        }

    async def update_data_source(
        self,
        *,
        data_source_id: str,
        title: str,
        properties: dict[str, object],
    ) -> dict[str, object]:
        self.updated_data_sources.append((data_source_id, title, properties))
        return {
            "id": data_source_id,
            "title": [{"type": "text", "text": {"content": title}}],
            "parent": {"database_id": "db-existing"},
        }

    async def create_page(
        self,
        *,
        data_source_id: str,
        properties: dict[str, object],
    ) -> NotionPageResult:
        self.created_pages.append((data_source_id, properties))
        return NotionPageResult(
            page_id="page-created",
            page_url="https://www.notion.so/page-created",
            created=True,
        )

    async def retrieve_page(
        self,
        *,
        page_id: str,
    ) -> dict[str, object]:
        return self.retrieved_pages[page_id]

    async def update_page(
        self,
        *,
        page_id: str,
        properties: dict[str, object],
    ) -> NotionPageResult:
        error = self.update_page_errors.get(page_id)
        if error is not None:
            raise error
        self.updated_pages.append((page_id, properties))
        return NotionPageResult(
            page_id=page_id,
            page_url=f"https://www.notion.so/{page_id}",
            created=False,
        )


def test_build_notion_data_source_properties_only_includes_expected_fields() -> None:
    properties = build_notion_data_source_properties()

    assert list(properties) == [
        TITLE_PROPERTY,
        PLATFORM_PROPERTY,
        LODGING_URL_PROPERTY,
        GOOGLE_MAPS_PROPERTY,
        AMENITIES_PROPERTY,
        DECISION_STATUS_PROPERTY,
        LAST_UPDATED_PROPERTY,
        DOCUMENT_ID_PROPERTY,
    ]
    assert {
        option["name"]
        for option in properties[PLATFORM_PROPERTY]["select"]["options"]
    } >= {"booking", "agoda", "airbnb", "unknown"}


def test_build_notion_page_properties_uses_reduced_readable_fields() -> None:
    candidate = NotionSyncCandidate(
        document_id="doc-123",
        platform="booking",
        url="https://short.example/doc-123",
        resolved_url="https://www.booking.com/hotel/jp/resol.html",
        property_name="Hotel Resol Ueno",
        amenities=("Wi-Fi", "早餐"),
        google_maps_url="https://maps.google.com/?q=hotel",
        last_updated_at=datetime(2026, 3, 27, 8, 30, tzinfo=timezone.utc),
    )

    properties = build_notion_page_properties(candidate)

    assert list(properties) == [
        TITLE_PROPERTY,
        PLATFORM_PROPERTY,
        LODGING_URL_PROPERTY,
        GOOGLE_MAPS_PROPERTY,
        AMENITIES_PROPERTY,
        DECISION_STATUS_PROPERTY,
        LAST_UPDATED_PROPERTY,
        DOCUMENT_ID_PROPERTY,
    ]
    assert properties[TITLE_PROPERTY]["title"][0]["text"]["content"] == "Hotel Resol Ueno"
    assert properties[PLATFORM_PROPERTY]["select"]["name"] == "booking"
    assert properties[LODGING_URL_PROPERTY]["url"] == candidate.resolved_url
    assert properties[GOOGLE_MAPS_PROPERTY]["url"] == candidate.google_maps_url
    assert properties[AMENITIES_PROPERTY]["rich_text"][0]["text"]["content"] == "Wi-Fi, 早餐"
    assert properties[DECISION_STATUS_PROPERTY]["select"]["name"] == "candidate"
    assert properties[LAST_UPDATED_PROPERTY]["date"]["start"] == "2026-03-27T08:30:00+00:00"
    assert properties[DOCUMENT_ID_PROPERTY]["rich_text"][0]["text"]["content"] == "doc-123"


def test_build_notion_page_properties_keeps_airbnb_platform() -> None:
    candidate = NotionSyncCandidate(
        document_id="doc-airbnb",
        platform="airbnb",
        url="https://www.airbnb.com/rooms/123456789",
        property_name="Shinjuku Loft",
        captured_at=datetime(2026, 3, 27, 8, 30, tzinfo=timezone.utc),
    )

    properties = build_notion_page_properties(candidate)

    assert properties[PLATFORM_PROPERTY]["select"]["name"] == "airbnb"
    assert properties[DECISION_STATUS_PROPERTY]["select"]["name"] == "candidate"
    assert (
        properties[LODGING_URL_PROPERTY]["url"]
        == "https://www.airbnb.com/rooms/123456789"
    )


def test_setup_database_updates_existing_data_source_schema() -> None:
    client = FakeNotionClient()
    service = NotionLodgingSyncService(
        client,
        data_source_id="ds-existing",
        database_title="住宿清單",
    )

    target = asyncio.run(service.setup_database())

    assert client.created_databases == []
    assert len(client.updated_data_sources) == 1
    updated_data_source_id, updated_title, properties = client.updated_data_sources[0]
    assert updated_data_source_id == "ds-existing"
    assert updated_title == "住宿清單"
    assert properties["title"]["name"] == TITLE_PROPERTY
    assert properties["captured-id"]["name"] == LAST_UPDATED_PROPERTY
    assert properties["city-id"] is None
    assert target.database_id == "db-existing"
    assert target.data_source_id == "ds-existing"
    assert target.title == "住宿清單"
    assert target.url == "https://www.notion.so/workspace/db-existing?v=view-shared"
    assert target.public_url == "https://www.notion.so/public-db-existing"


def test_get_database_url_prefers_public_url_from_retrieved_database() -> None:
    client = FakeNotionClient()
    service = NotionLodgingSyncService(
        client,
        database_id="db-existing",
        data_source_id="ds-existing",
    )

    result = asyncio.run(service.get_database_url(prefer_public=True))

    assert result == "https://www.notion.so/public-db-existing"
    assert client.retrieved_databases == ["db-existing"]


def test_build_notion_data_source_update_properties_renames_and_removes_old_fields() -> None:
    properties = build_notion_data_source_update_properties(
        {
            "properties": {
                "Name": {"id": "title", "type": "title"},
                "Platform": {"id": "platform-id", "type": "select"},
                "Amenities": {"id": "amenities-id", "type": "rich_text"},
                "Captured At": {"id": "captured-id", "type": "date"},
                "Document ID": {"id": "document-id", "type": "rich_text"},
                "City": {"id": "city-id", "type": "rich_text"},
            }
        }
    )

    assert properties["title"]["name"] == TITLE_PROPERTY
    assert properties["platform-id"]["name"] == PLATFORM_PROPERTY
    assert properties["amenities-id"]["name"] == AMENITIES_PROPERTY
    assert properties["captured-id"]["name"] == LAST_UPDATED_PROPERTY
    assert properties["document-id"]["name"] == DOCUMENT_ID_PROPERTY
    assert properties["city-id"] is None
    assert {
        option["name"]
        for option in properties["platform-id"]["select"]["options"]
    } >= {"booking", "agoda", "airbnb", "unknown"}
    assert LODGING_URL_PROPERTY in properties
    assert GOOGLE_MAPS_PROPERTY in properties
    assert DECISION_STATUS_PROPERTY in properties


def test_build_candidate_uses_latest_source_timestamp_for_last_updated() -> None:
    candidate = _build_candidate(
        {
            "_id": "doc-123",
            "platform": "agoda",
            "url": "https://www.agoda.com/foo",
            "captured_at": datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc),
            "map_resolved_at": datetime(2026, 3, 26, 9, 0, tzinfo=timezone.utc),
            "details_resolved_at": datetime(2026, 3, 27, 7, 0, tzinfo=timezone.utc),
            "pricing_resolved_at": datetime(2026, 3, 27, 6, 0, tzinfo=timezone.utc),
            "decision_updated_at": datetime(2026, 3, 28, 6, 0, tzinfo=timezone.utc),
            "decision_status": "booked",
        }
    )

    assert candidate.last_updated_at == datetime(
        2026,
        3,
        28,
        6,
        0,
        tzinfo=timezone.utc,
    )
    assert candidate.decision_status == "booked"


def test_sync_document_recreates_page_when_existing_page_belongs_to_other_data_source() -> None:
    client = FakeNotionClient()
    client.retrieved_pages["page-old"] = {
        "parent": {"data_source_id": "ds-old"},
    }
    service = NotionLodgingSyncService(
        client,
        database_id="db-current",
        data_source_id="ds-current",
    )
    candidate = NotionSyncCandidate(
        document_id="doc-123",
        platform="booking",
        url="https://www.booking.com/hotel/jp/resol.html",
        notion_page_id="page-old",
    )

    result = asyncio.run(service.sync_document(candidate))

    assert result.created is True
    assert client.updated_pages == []
    assert len(client.created_pages) == 1
    assert client.created_pages[0][0] == "ds-current"


def test_sync_document_updates_page_when_existing_page_belongs_to_current_data_source() -> None:
    client = FakeNotionClient()
    service = NotionLodgingSyncService(
        client,
        database_id="db-current",
        data_source_id="ds-current",
    )
    candidate = NotionSyncCandidate(
        document_id="doc-123",
        platform="booking",
        url="https://www.booking.com/hotel/jp/resol.html",
        notion_page_id="page-current",
        notion_data_source_id="ds-current",
    )

    result = asyncio.run(service.sync_document(candidate))

    assert result.created is False
    assert client.created_pages == []
    assert len(client.updated_pages) == 1
    assert client.updated_pages[0][0] == "page-current"


def test_sync_document_recreates_page_when_existing_page_is_archived() -> None:
    client = FakeNotionClient()
    client.update_page_errors["page-archived"] = NotionApiError(
        "Can't edit block that is archived. You must unarchive the block before editing."
    )
    service = NotionLodgingSyncService(
        client,
        database_id="db-current",
        data_source_id="ds-current",
    )
    candidate = NotionSyncCandidate(
        document_id="doc-123",
        platform="booking",
        url="https://www.booking.com/hotel/jp/resol.html",
        notion_page_id="page-archived",
        notion_data_source_id="ds-current",
    )

    result = asyncio.run(service.sync_document(candidate))

    assert result.created is True
    assert client.updated_pages == []
    assert len(client.created_pages) == 1
    assert client.created_pages[0][0] == "ds-current"
