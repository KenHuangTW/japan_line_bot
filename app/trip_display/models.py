from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

TripDisplayAvailability = Literal["all", "available", "sold_out", "unknown"]
TripDisplaySort = Literal[
    "captured_desc",
    "captured_asc",
    "price_asc",
    "price_desc",
]


@dataclass(frozen=True)
class TripDisplayFilters:
    platform: str | None = None
    availability: TripDisplayAvailability = "all"
    sort: TripDisplaySort = "captured_desc"


@dataclass(frozen=True)
class TripDisplayLodging:
    document_id: str
    platform: str
    url: str
    resolved_url: str | None = None
    property_name: str | None = None
    city: str | None = None
    hero_image_url: str | None = None
    line_hero_image_url: str | None = None
    formatted_address: str | None = None
    price_amount: float | None = None
    price_currency: str | None = None
    is_sold_out: bool | None = None
    amenities: tuple[str, ...] = ()
    google_maps_url: str | None = None
    google_maps_search_url: str | None = None
    notion_page_url: str | None = None
    captured_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def display_name(self) -> str:
        return self.property_name or self.target_url

    @property
    def target_url(self) -> str:
        return self.resolved_url or self.url

    @property
    def maps_url(self) -> str | None:
        return self.google_maps_url or self.google_maps_search_url

    @property
    def availability_key(self) -> TripDisplayAvailability:
        if self.is_sold_out is True:
            return "sold_out"
        if self.is_sold_out is False:
            return "available"
        return "unknown"

    @property
    def availability_label(self) -> str:
        labels = {
            "available": "可訂",
            "sold_out": "已售完",
            "unknown": "待確認",
        }
        return labels[self.availability_key]

    @property
    def price_label(self) -> str:
        if self.price_amount is None or not self.price_currency:
            return "價格待確認"
        return f"{self.price_currency} {self.price_amount:,.0f}"


@dataclass(frozen=True)
class TripDisplaySurface:
    trip_id: str
    trip_title: str
    trip_status: str
    display_token: str
    filters: TripDisplayFilters
    lodgings: tuple[TripDisplayLodging, ...]
    total_lodgings: int
    available_count: int
    sold_out_count: int
    unknown_count: int
    notion_export_url: str | None = None
    generated_at: datetime | None = None
    platform_options: tuple[str, ...] = ()

    @property
    def visible_count(self) -> int:
        return len(self.lodgings)

    def to_summary_payload(self) -> dict[str, Any]:
        return {
            "trip": {
                "trip_id": self.trip_id,
                "title": self.trip_title,
                "status": self.trip_status,
                "display_token": self.display_token,
            },
            "filters": {
                "platform": self.filters.platform,
                "availability": self.filters.availability,
                "sort": self.filters.sort,
            },
            "summary": {
                "total_lodgings": self.total_lodgings,
                "visible_lodgings": self.visible_count,
                "available_count": self.available_count,
                "sold_out_count": self.sold_out_count,
                "unknown_count": self.unknown_count,
                "notion_export_url": self.notion_export_url,
            },
            "lodgings": [
                {
                    "document_id": lodging.document_id,
                    "platform": lodging.platform,
                    "property_name": lodging.property_name,
                    "display_name": lodging.display_name,
                    "city": lodging.city,
                    "hero_image_url": lodging.hero_image_url,
                    "line_hero_image_url": lodging.line_hero_image_url,
                    "target_url": lodging.target_url,
                    "formatted_address": lodging.formatted_address,
                    "price_amount": lodging.price_amount,
                    "price_currency": lodging.price_currency,
                    "availability": lodging.availability_key,
                    "is_sold_out": lodging.is_sold_out,
                    "amenities": list(lodging.amenities),
                    "maps_url": lodging.maps_url,
                    "notion_page_url": lodging.notion_page_url,
                    "captured_at": (
                        lodging.captured_at.isoformat()
                        if lodging.captured_at is not None
                        else None
                    ),
                    "updated_at": (
                        lodging.updated_at.isoformat()
                        if lodging.updated_at is not None
                        else None
                    ),
                }
                for lodging in self.lodgings
            ],
        }
