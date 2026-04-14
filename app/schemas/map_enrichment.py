from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MapEnrichmentRunRequest(BaseModel):
    limit: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="本次最多處理幾筆待解析住宿資料。",
    )


class MapEnrichmentRunResponse(BaseModel):
    processed: int
    resolved: int
    partial: int
    details_resolved: int
    pricing_resolved: int
    failed: int
    limit_used: int


class MapEnrichmentRetryResponse(BaseModel):
    document_id: str
    processed: int
    resolved: int
    partial: int
    details_resolved: int
    pricing_resolved: int
    failed: int


class MapEnrichmentDocumentResponse(BaseModel):
    document_id: str
    url: str
    resolved_url: str | None = None
    map_status: str | None = None
    map_source: str | None = None
    details_status: str | None = None
    details_source: str | None = None
    pricing_status: str | None = None
    pricing_source: str | None = None
    property_name: str | None = None
    hero_image_url: str | None = None
    line_hero_image_url: str | None = None
    formatted_address: str | None = None
    street_address: str | None = None
    district: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_name: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    property_type: str | None = None
    room_count: int | None = None
    bedroom_count: int | None = None
    bathroom_count: float | None = None
    amenities: list[str] = Field(default_factory=list)
    price_amount: float | None = None
    price_currency: str | None = None
    source_price_amount: float | None = None
    source_price_currency: str | None = None
    price_exchange_rate: float | None = None
    price_exchange_rate_source: str | None = None
    is_sold_out: bool | None = None
    availability_source: str | None = None
    google_maps_url: str | None = None
    google_maps_search_url: str | None = None
    map_error: str | None = None
    map_retry_count: int = 0
    details_error: str | None = None
    details_retry_count: int = 0
    pricing_error: str | None = None
    pricing_retry_count: int = 0
    captured_at: datetime | None = None


class MapEnrichmentDocumentsResponse(BaseModel):
    documents: list[MapEnrichmentDocumentResponse]
    count: int
    limit_used: int
    statuses: list[str]
