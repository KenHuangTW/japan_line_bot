from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ParsedLodgingMap:
    property_name: str | None = None
    formatted_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_id: str | None = None
    map_source: str | None = None


@dataclass(frozen=True)
class EnrichedLodgingMap:
    resolved_url: str | None = None
    resolved_hostname: str | None = None
    property_name: str | None = None
    formatted_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_id: str | None = None
    google_maps_url: str | None = None
    google_maps_search_url: str | None = None
    map_source: str | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True)
class MapEnrichmentCandidate:
    document_id: Any
    url: str
    resolved_url: str | None = None

    @property
    def target_url(self) -> str:
        return self.resolved_url or self.url


@dataclass(frozen=True)
class MapEnrichmentDocument:
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
