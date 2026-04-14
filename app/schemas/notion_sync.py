from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NotionSourceScopeFields(BaseModel):
    source_type: str | None = Field(
        default=None,
        description="LINE source 類型，可為 group、room、user。",
    )
    group_id: str | None = Field(
        default=None,
        description="當 source_type=group 時的 LINE group id。",
    )
    room_id: str | None = Field(
        default=None,
        description="當 source_type=room 時的 LINE room id。",
    )
    user_id: str | None = Field(
        default=None,
        description="當 source_type=user 時的 LINE user id。",
    )
    trip_id: str | None = Field(
        default=None,
        description="旅次識別碼。",
    )
    trip_title: str | None = Field(
        default=None,
        description="旅次名稱。",
    )


class NotionSetupRequest(NotionSourceScopeFields):
    title: str | None = Field(
        default=None,
        description="要建立在 Notion 中的資料庫名稱。",
    )
    parent_page_id: str | None = Field(
        default=None,
        description="若要建立 scoped database，可指定新的 Notion parent page id。",
    )
    data_source_id: str | None = Field(
        default=None,
        description="若要綁定 scoped target，可指定既有 Notion data source id。",
    )


class NotionSetupResponse(NotionSourceScopeFields):
    database_id: str
    data_source_id: str
    database_title: str | None = None
    database_url: str | None = None
    database_public_url: str | None = None
    target_source: str | None = None


class NotionSyncRunRequest(NotionSourceScopeFields):
    limit: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="本次最多同步幾筆住宿資料。",
    )
    force: bool = Field(
        default=False,
        description="是否忽略 pending/outdated 篩選，直接重跑所有資料。",
    )


class NotionSyncRunResponse(NotionSourceScopeFields):
    processed: int
    created: int
    updated: int
    failed: int
    limit_used: int
    database_id: str | None = None
    data_source_id: str | None = None
    target_source: str | None = None


class NotionSyncRetryResponse(BaseModel):
    document_id: str
    processed: int
    created: int
    updated: int
    failed: int
    notion_page_id: str | None = None
    notion_page_url: str | None = None


class NotionSyncDocumentResponse(NotionSourceScopeFields):
    document_id: str
    platform: str
    url: str
    resolved_url: str | None = None
    property_name: str | None = None
    formatted_address: str | None = None
    city: str | None = None
    country_code: str | None = None
    property_type: str | None = None
    amenities: list[str] = Field(default_factory=list)
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


class NotionSyncDocumentsResponse(BaseModel):
    documents: list[NotionSyncDocumentResponse]
    count: int
    limit_used: int
    statuses: list[str]
