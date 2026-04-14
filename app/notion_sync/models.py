from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NotionDatabaseTarget:
    database_id: str
    data_source_id: str
    title: str | None = None
    url: str | None = None
    public_url: str | None = None

    @property
    def share_url(self) -> str | None:
        return self.public_url or self.url


@dataclass(frozen=True)
class NotionPageResult:
    page_id: str
    page_url: str | None = None
    created: bool = False


@dataclass(frozen=True)
class NotionSyncSourceScope:
    source_type: str
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    trip_id: str | None = None
    trip_title: str | None = None


@dataclass(frozen=True)
class NotionSyncCandidate:
    document_id: Any
    platform: str
    url: str
    resolved_url: str | None = None
    property_name: str | None = None
    formatted_address: str | None = None
    city: str | None = None
    country_code: str | None = None
    property_type: str | None = None
    amenities: tuple[str, ...] = ()
    price_amount: float | None = None
    price_currency: str | None = None
    is_sold_out: bool | None = None
    google_maps_url: str | None = None
    google_maps_search_url: str | None = None
    map_status: str | None = None
    details_status: str | None = None
    pricing_status: str | None = None
    captured_at: datetime | None = None
    last_updated_at: datetime | None = None
    source_type: str | None = None
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    trip_id: str | None = None
    trip_title: str | None = None
    notion_page_id: str | None = None
    notion_database_id: str | None = None
    notion_data_source_id: str | None = None

    @property
    def target_url(self) -> str:
        return self.resolved_url or self.url

    @property
    def maps_url(self) -> str | None:
        return self.google_maps_url or self.google_maps_search_url

    @property
    def display_name(self) -> str:
        return self.property_name or self.target_url or str(self.document_id)


@dataclass(frozen=True)
class NotionSyncDocument:
    document_id: str
    platform: str
    url: str
    resolved_url: str | None = None
    property_name: str | None = None
    formatted_address: str | None = None
    city: str | None = None
    country_code: str | None = None
    property_type: str | None = None
    amenities: tuple[str, ...] = ()
    price_amount: float | None = None
    price_currency: str | None = None
    is_sold_out: bool | None = None
    google_maps_url: str | None = None
    google_maps_search_url: str | None = None
    map_status: str | None = None
    details_status: str | None = None
    pricing_status: str | None = None
    notion_page_id: str | None = None
    notion_page_url: str | None = None
    notion_sync_status: str = "pending"
    notion_sync_error: str | None = None
    notion_sync_retry_count: int = 0
    notion_last_attempt_at: datetime | None = None
    notion_last_synced_at: datetime | None = None
    captured_at: datetime | None = None
    last_updated_at: datetime | None = None
    source_type: str | None = None
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    trip_id: str | None = None
    trip_title: str | None = None
    notion_database_id: str | None = None
    notion_data_source_id: str | None = None


@dataclass(frozen=True)
class NotionSyncSummary:
    processed: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
