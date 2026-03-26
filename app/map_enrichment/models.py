from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ParsedLodgingMap:
    property_name: str | None = None
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
    place_id: str | None = None
    map_source: str | None = None
    property_type: str | None = None
    room_count: int | None = None
    bedroom_count: int | None = None
    bathroom_count: float | None = None
    amenities: tuple[str, ...] = ()
    details_source: str | None = None
    price_amount: float | None = None
    price_currency: str | None = None
    pricing_source: str | None = None
    is_sold_out: bool | None = None
    availability_source: str | None = None

    @property
    def has_details(self) -> bool:
        return any(
            (
                self.property_type,
                self.room_count is not None,
                self.bedroom_count is not None,
                self.bathroom_count is not None,
                bool(self.amenities),
            )
        )

    @property
    def has_pricing(self) -> bool:
        return self.price_amount is not None


@dataclass(frozen=True)
class EnrichedLodgingMap:
    resolved_url: str | None = None
    resolved_hostname: str | None = None
    property_name: str | None = None
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
    place_id: str | None = None
    google_maps_url: str | None = None
    google_maps_search_url: str | None = None
    map_source: str | None = None
    property_type: str | None = None
    room_count: int | None = None
    bedroom_count: int | None = None
    bathroom_count: float | None = None
    amenities: tuple[str, ...] = ()
    details_source: str | None = None
    price_amount: float | None = None
    price_currency: str | None = None
    source_price_amount: float | None = None
    source_price_currency: str | None = None
    price_exchange_rate: float | None = None
    price_exchange_rate_source: str | None = None
    pricing_source: str | None = None
    is_sold_out: bool | None = None
    availability_source: str | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def has_details(self) -> bool:
        return any(
            (
                self.property_type,
                self.room_count is not None,
                self.bedroom_count is not None,
                self.bathroom_count is not None,
                bool(self.amenities),
            )
        )

    @property
    def has_pricing(self) -> bool:
        return self.price_amount is not None


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
    details_status: str | None = None
    details_source: str | None = None
    pricing_status: str | None = None
    pricing_source: str | None = None
    property_name: str | None = None
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
    amenities: tuple[str, ...] = ()
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
