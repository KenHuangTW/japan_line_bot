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
    failed: int
    limit_used: int


class MapEnrichmentRetryResponse(BaseModel):
    document_id: str
    processed: int
    resolved: int
    partial: int
    failed: int


class MapEnrichmentDocumentResponse(BaseModel):
    document_id: str
    url: str
    resolved_url: str | None = None
    map_status: str | None = None
    map_source: str | None = None
    property_name: str | None = None
    formatted_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    google_maps_search_url: str | None = None
    map_error: str | None = None
    map_retry_count: int = 0
    captured_at: datetime | None = None


class MapEnrichmentDocumentsResponse(BaseModel):
    documents: list[MapEnrichmentDocumentResponse]
    count: int
    limit_used: int
    statuses: list[str]
