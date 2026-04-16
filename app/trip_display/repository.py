from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from app.line_media import normalize_line_image_url
from app.models import LineTrip
from app.notion_sync import NotionTargetRepository, build_source_scope
from app.trip_display.models import (
    TripDisplayFilters,
    TripDisplayLodging,
    TripDisplaySort,
    TripDisplaySurface,
)

UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class MongoCursor(Protocol):
    def sort(self, key: str, direction: int) -> "MongoCursor": ...

    def __iter__(self): ...


class MongoCollection(Protocol):
    def find(self, *args: Any, **kwargs: Any) -> MongoCursor: ...


class TripDisplayRepository(Protocol):
    def build_trip_display(
        self,
        trip: LineTrip,
        filters: TripDisplayFilters | None = None,
    ) -> TripDisplaySurface: ...


class MongoTripDisplayRepository:
    def __init__(
        self,
        collection: MongoCollection,
        notion_target_repository: NotionTargetRepository | None = None,
    ) -> None:
        self.collection = collection
        self.notion_target_repository = notion_target_repository

    def build_trip_display(
        self,
        trip: LineTrip,
        filters: TripDisplayFilters | None = None,
    ) -> TripDisplaySurface:
        active_filters = filters or TripDisplayFilters()
        documents = list(
            self.collection.find(_build_trip_query(trip)).sort("captured_at", -1)
        )
        all_lodgings = tuple(_build_lodging(document) for document in documents)
        notion_export_url = _resolve_notion_export_url(
            trip=trip,
            notion_target_repository=self.notion_target_repository,
        )
        filtered_lodgings = _sort_lodgings(
            _filter_lodgings(all_lodgings, active_filters),
            active_filters.sort,
        )
        available_count = sum(
            1 for lodging in all_lodgings if lodging.availability_key == "available"
        )
        sold_out_count = sum(
            1 for lodging in all_lodgings if lodging.availability_key == "sold_out"
        )
        unknown_count = sum(
            1 for lodging in all_lodgings if lodging.availability_key == "unknown"
        )
        platform_options = tuple(
            sorted({lodging.platform for lodging in all_lodgings if lodging.platform})
        )
        generated_at = max(
            (
                lodging.updated_at or lodging.captured_at
                for lodging in all_lodgings
                if lodging.updated_at is not None or lodging.captured_at is not None
            ),
            default=None,
        )

        return TripDisplaySurface(
            trip_id=trip.trip_id,
            trip_title=trip.title,
            trip_status=trip.status,
            display_token=trip.display_token,
            filters=active_filters,
            lodgings=filtered_lodgings,
            total_lodgings=len(all_lodgings),
            available_count=available_count,
            sold_out_count=sold_out_count,
            unknown_count=unknown_count,
            notion_export_url=notion_export_url,
            generated_at=generated_at,
            platform_options=platform_options,
        )


def _build_trip_query(trip: LineTrip) -> dict[str, Any]:
    query: dict[str, Any] = {
        "source_type": trip.source_type,
        "trip_id": trip.trip_id,
    }
    if trip.source_type == "group":
        query["group_id"] = trip.group_id
    elif trip.source_type == "room":
        query["room_id"] = trip.room_id
    elif trip.source_type == "user":
        query["user_id"] = trip.user_id
    return query


def _build_lodging(document: dict[str, Any]) -> TripDisplayLodging:
    return TripDisplayLodging(
        document_id=str(document.get("_id") or document.get("document_id") or ""),
        platform=str(document.get("platform") or ""),
        url=str(document.get("url") or ""),
        resolved_url=document.get("resolved_url"),
        property_name=document.get("property_name"),
        city=document.get("city"),
        hero_image_url=document.get("hero_image_url"),
        line_hero_image_url=(
            document.get("line_hero_image_url")
            or normalize_line_image_url(document.get("hero_image_url"))
        ),
        formatted_address=document.get("formatted_address"),
        price_amount=document.get("price_amount"),
        price_currency=document.get("price_currency"),
        is_sold_out=document.get("is_sold_out"),
        amenities=tuple(
            item
            for item in (document.get("amenities") or [])
            if isinstance(item, str) and item.strip()
        ),
        google_maps_url=document.get("google_maps_url"),
        google_maps_search_url=document.get("google_maps_search_url"),
        notion_page_url=document.get("notion_page_url"),
        captured_at=document.get("captured_at"),
        updated_at=_resolve_updated_at(document),
    )


def _resolve_updated_at(document: dict[str, Any]) -> datetime | None:
    timestamps = [
        value
        for value in (
            document.get("captured_at"),
            document.get("map_resolved_at"),
            document.get("details_resolved_at"),
            document.get("pricing_resolved_at"),
            document.get("notion_last_synced_at"),
        )
        if isinstance(value, datetime)
    ]
    if not timestamps:
        return None
    return max(timestamps)


def _resolve_notion_export_url(
    *,
    trip: LineTrip,
    notion_target_repository: NotionTargetRepository | None,
) -> str | None:
    if notion_target_repository is None:
        return None

    source_scope = build_source_scope(
        source_type=trip.source_type,
        group_id=trip.group_id,
        room_id=trip.room_id,
        user_id=trip.user_id,
        trip_id=trip.trip_id,
        trip_title=trip.title,
    )
    if source_scope is None:
        return None

    target = notion_target_repository.find_by_source_scope(source_scope)
    if target is None:
        return None
    return target.share_url


def _filter_lodgings(
    lodgings: Sequence[TripDisplayLodging],
    filters: TripDisplayFilters,
) -> tuple[TripDisplayLodging, ...]:
    platform = filters.platform.strip().lower() if filters.platform else None
    results = lodgings
    if platform is not None:
        results = tuple(
            lodging for lodging in results if lodging.platform.lower() == platform
        )
    if filters.availability != "all":
        results = tuple(
            lodging
            for lodging in results
            if lodging.availability_key == filters.availability
        )
    return tuple(results)


def _sort_lodgings(
    lodgings: Sequence[TripDisplayLodging],
    sort: TripDisplaySort,
) -> tuple[TripDisplayLodging, ...]:
    if sort == "captured_asc":
        return tuple(sorted(lodgings, key=_captured_sort_key))
    if sort == "price_asc":
        return tuple(sorted(lodgings, key=_price_asc_sort_key))
    if sort == "price_desc":
        return tuple(sorted(lodgings, key=_price_desc_sort_key))
    return tuple(sorted(lodgings, key=_captured_sort_key, reverse=True))


def _captured_sort_key(lodging: TripDisplayLodging) -> tuple[bool, datetime]:
    timestamp = lodging.captured_at or lodging.updated_at or UTC_EPOCH
    return lodging.captured_at is None and lodging.updated_at is None, timestamp


def _price_asc_sort_key(lodging: TripDisplayLodging) -> tuple[bool, float, datetime]:
    fallback_time = lodging.captured_at or lodging.updated_at or UTC_EPOCH
    if lodging.price_amount is None:
        return True, float("inf"), fallback_time
    return False, lodging.price_amount, fallback_time


def _price_desc_sort_key(lodging: TripDisplayLodging) -> tuple[bool, float, datetime]:
    fallback_time = lodging.captured_at or lodging.updated_at or UTC_EPOCH
    if lodging.price_amount is None:
        return True, float("inf"), fallback_time
    return False, -lodging.price_amount, fallback_time
