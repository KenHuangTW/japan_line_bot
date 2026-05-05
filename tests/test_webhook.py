from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.config import Settings
from app.lodging_summary import (
    LodgingDecisionSummaryEmptyTripError,
    LodgingDecisionSummaryInvalidResponseError,
    LodgingDecisionSummaryResult,
    LodgingDecisionSummaryTimeoutError,
)
from app.lodging_links.common import build_lodging_lookup_keys
from app.lodging_links.service import LodgingLinkService
from app.line_security import generate_signature
from app.main import create_app as build_app
from app.map_enrichment.models import EnrichedLodgingMap, MapEnrichmentCandidate
from app.models import CapturedLodgingLink, LineTrip
from app.schemas.lodging_summary import (
    LodgingDecisionCandidate,
    LodgingDecisionSummaryLodging,
    LodgingDecisionSummaryRequest,
    LodgingDecisionSummaryResponse,
    LodgingDecisionSummaryStats,
    LodgingDecisionSummaryTrip,
)
from app.source_scope import SourceScope
from app.trip_display import MongoTripDisplayRepository

DEFAULT_TRIP_ID = "trip-current"
DEFAULT_TRIP_TITLE = "東京 2026"


class FakeLineClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.message_calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def reply_messages(
        self,
        reply_token: str,
        messages: list[dict[str, Any]],
    ) -> None:
        self.message_calls.append((reply_token, messages))

    async def reply_text(self, reply_token: str, text: str) -> None:
        self.calls.append((reply_token, text))


class FailingLineClient:
    async def reply_messages(
        self,
        reply_token: str,
        messages: list[dict[str, Any]],
    ) -> None:
        raise RuntimeError("simulated LINE reply failure")

    async def reply_text(self, reply_token: str, text: str) -> None:
        raise RuntimeError("simulated LINE reply failure")


class FlexFailingLineClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.message_calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def reply_messages(
        self,
        reply_token: str,
        messages: list[dict[str, Any]],
    ) -> None:
        self.message_calls.append((reply_token, messages))
        raise RuntimeError("simulated flex reply failure")

    async def reply_text(self, reply_token: str, text: str) -> None:
        self.calls.append((reply_token, text))


class FakeDecisionSummaryService:
    def __init__(
        self,
        *,
        result: LodgingDecisionSummaryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def summarize_trip(self, trip: LineTrip) -> LodgingDecisionSummaryResult:
        self.calls.append(trip.trip_id)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class FakeLodgingUrlResolver:
    def __init__(self, resolved_urls: dict[str, str | None] | None = None) -> None:
        self.resolved_urls = resolved_urls or {}
        self.calls: list[str] = []

    async def resolve(self, url: str) -> str | None:
        self.calls.append(url)
        return self.resolved_urls.get(url)


class InMemoryCapturedLinkRepository:
    def __init__(self) -> None:
        self.items: list[CapturedLodgingLink] = []

    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        self.items.extend(items)
        return len(items)

    def find_duplicate(
        self,
        urls: Sequence[str],
        *,
        source_type: str,
        trip_id: str | None = None,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
    ) -> CapturedLodgingLink | None:
        candidate_keys = set(build_lodging_lookup_keys(*urls))
        if not candidate_keys:
            return None

        matches = [
            item
            for item in self.items
            if _matches_captured_source(
                item,
                source_type=source_type,
                trip_id=trip_id,
                group_id=group_id,
                room_id=room_id,
                user_id=user_id,
            )
            and candidate_keys.intersection(
                build_lodging_lookup_keys(item.url, item.resolved_url)
            )
        ]
        if not matches:
            return None

        return min(matches, key=lambda item: (len(item.url), -item.captured_at.timestamp()))

    def update_decision_status(
        self,
        document_id: str,
        *,
        decision_status,
        source_type: str,
        trip_id: str | None = None,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
        updated_by_user_id: str | None = None,
    ) -> CapturedLodgingLink | None:
        for index, item in enumerate(self.items, start=1):
            if document_id != f"doc-{index}":
                continue
            if not _matches_captured_source(
                item,
                source_type=source_type,
                trip_id=trip_id,
                group_id=group_id,
                room_id=room_id,
                user_id=user_id,
            ):
                return None
            updated = item.model_copy(
                update={
                    "decision_status": decision_status,
                    "decision_updated_at": datetime.now(timezone.utc),
                    "decision_updated_by_user_id": updated_by_user_id,
                }
            )
            self.items[index - 1] = updated
            return updated
        return None


class InMemoryTripRepository:
    def __init__(self, trips: Sequence[LineTrip] | None = None) -> None:
        self.trips = [trip.model_copy() for trip in trips or []]
        self.next_trip_number = len(self.trips) + 1

    def create_trip(self, source_scope: SourceScope, title: str) -> LineTrip:
        normalized_title = _normalize_trip_title(title)
        for trip in self.trips:
            if _matches_trip_source(trip, source_scope):
                trip.is_active = False
        trip = LineTrip(
            trip_id=f"trip-{self.next_trip_number}",
            title=normalized_title,
            source_type=source_scope.source_type,
            group_id=source_scope.group_id,
            room_id=source_scope.room_id,
            user_id=source_scope.user_id,
        )
        self.next_trip_number += 1
        self.trips.append(trip)
        return trip.model_copy()

    def find_open_trip_by_title(
        self,
        source_scope: SourceScope,
        title: str,
    ) -> LineTrip | None:
        normalized_title = _normalize_trip_title(title)
        for trip in self.trips:
            if (
                _matches_trip_source(trip, source_scope)
                and trip.status == "open"
                and trip.title == normalized_title
            ):
                return trip.model_copy()
        return None

    def get_active_trip(self, source_scope: SourceScope) -> LineTrip | None:
        for trip in self.trips:
            if (
                _matches_trip_source(trip, source_scope)
                and trip.status == "open"
                and trip.is_active
            ):
                return trip.model_copy()
        return None

    def find_trip_by_display_token(self, display_token: str) -> LineTrip | None:
        normalized_token = display_token.strip()
        for trip in self.trips:
            if trip.display_token == normalized_token:
                return trip.model_copy()
        return None

    def switch_active_trip(
        self,
        source_scope: SourceScope,
        title: str,
    ) -> LineTrip | None:
        normalized_title = _normalize_trip_title(title)
        target_trip: LineTrip | None = None
        for trip in self.trips:
            if (
                _matches_trip_source(trip, source_scope)
                and trip.status == "open"
                and trip.title == normalized_title
            ):
                target_trip = trip
                break
        if target_trip is None:
            return None

        for trip in self.trips:
            if _matches_trip_source(trip, source_scope) and trip.status == "open":
                trip.is_active = trip.trip_id == target_trip.trip_id
        return target_trip.model_copy() if target_trip is not None else None

    def archive_active_trip(
        self,
        source_scope: SourceScope,
    ) -> LineTrip | None:
        for trip in self.trips:
            if (
                _matches_trip_source(trip, source_scope)
                and trip.status == "open"
                and trip.is_active
            ):
                trip.status = "archived"
                trip.is_active = False
                trip.archived_at = datetime.now(timezone.utc)
                return trip.model_copy()
        return None


def create_app(
    *,
    trip_repository: InMemoryTripRepository | None = None,
    active_trip: bool = True,
    trip_id: str = DEFAULT_TRIP_ID,
    trip_display_token: str = "trip-display-current",
    trip_title: str = DEFAULT_TRIP_TITLE,
    trip_source_type: str = "group",
    trip_group_id: str | None = "Cgroup123",
    trip_room_id: str | None = None,
    trip_user_id: str | None = "Uuser123",
    **kwargs: Any,
):
    resolved_trip_repository = trip_repository
    if resolved_trip_repository is None:
        initial_trips: list[LineTrip] = []
        if active_trip:
            initial_trips.append(
                _build_trip(
                    trip_id=trip_id,
                    display_token=trip_display_token,
                    title=trip_title,
                    source_type=trip_source_type,
                    group_id=trip_group_id,
                    room_id=trip_room_id,
                    user_id=trip_user_id,
                )
            )
        resolved_trip_repository = InMemoryTripRepository(initial_trips)
    return build_app(
        trip_repository=resolved_trip_repository,
        **kwargs,
    )


class TripDisplayCursor:
    def __init__(self, documents: Sequence[dict[str, Any]]) -> None:
        self.documents = [dict(document) for document in documents]

    def sort(self, key: str, direction: int) -> "TripDisplayCursor":
        self.documents.sort(
            key=lambda item: item.get(key),
            reverse=direction < 0,
        )
        return self

    def __iter__(self):
        return iter(self.documents)


class TripDisplayCollection:
    def __init__(self, documents: Sequence[dict[str, Any]]) -> None:
        self.documents = [dict(document) for document in documents]

    def find(self, query: dict[str, Any]) -> TripDisplayCursor:
        matches = [
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]
        return TripDisplayCursor(matches)


def _build_trip_display_repository(
    items: Sequence[CapturedLodgingLink],
):
    documents = []
    for index, item in enumerate(items, start=1):
        document = item.model_dump(mode="python")
        document["_id"] = f"doc-{index}"
        documents.append(document)
    return MongoTripDisplayRepository(
        TripDisplayCollection(documents),
    )


def _single_message_call(
    fake_line_client: FakeLineClient,
) -> tuple[str, list[dict[str, Any]]]:
    assert len(fake_line_client.message_calls) == 1
    return fake_line_client.message_calls[0]


class InMemoryMapEnrichmentRepository:
    def __init__(
        self,
        *,
        pending_items: Sequence[MapEnrichmentCandidate] | None = None,
        all_items: Sequence[MapEnrichmentCandidate] | None = None,
    ) -> None:
        self.pending_items = list(pending_items or [])
        self.all_items = list(all_items or self.pending_items)
        self.pending_limits: list[int | None] = []
        self.all_limits: list[int | None] = []
        self.pending_source_scopes: list[SourceScope | None] = []
        self.all_source_scopes: list[SourceScope | None] = []
        self.resolved: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: SourceScope | None = None,
    ):
        self.pending_limits.append(limit)
        self.pending_source_scopes.append(source_scope)
        items = self.pending_items
        if limit is None:
            return items
        return items[:limit]

    def find_all(
        self,
        limit: int | None = None,
        source_scope: SourceScope | None = None,
    ):
        self.all_limits.append(limit)
        self.all_source_scopes.append(source_scope)
        items = self.all_items
        if limit is None:
            return items
        return items[:limit]

    def find_failed(
        self,
        limit: int,
        source_scope: SourceScope | None = None,
    ):
        raise NotImplementedError

    def find_by_document_id(self, document_id: str):
        raise NotImplementedError

    def list_documents(self, limit: int, statuses=None, source_scope=None):
        raise NotImplementedError

    def mark_resolved(self, document_id, enrichment: EnrichedLodgingMap) -> None:
        self.resolved.append(str(document_id))

    def mark_failed(self, document_id, error: str) -> None:
        self.failed.append((str(document_id), error))


class FakeMapEnrichmentService:
    def __init__(self, results: dict[str, EnrichedLodgingMap | None]) -> None:
        self.results = results
        self.calls: list[str] = []

    async def enrich(self, url: str) -> EnrichedLodgingMap | None:
        self.calls.append(url)
        return self.results.get(url)


@dataclass
class StoredCapturedDocument:
    document_id: str
    item: CapturedLodgingLink


class SharedCapturedDocumentStore:
    def __init__(self) -> None:
        self.documents: list[StoredCapturedDocument] = []
        self.next_document_number = 1

    def add_document(
        self,
        item: CapturedLodgingLink,
        *,
        document_id: str | None = None,
    ) -> str:
        assigned_document_id = document_id or f"doc-{self.next_document_number}"
        document_number = _extract_document_number(assigned_document_id)
        if document_number is not None:
            self.next_document_number = max(
                self.next_document_number,
                document_number + 1,
            )
        self.documents.append(
            StoredCapturedDocument(
                document_id=assigned_document_id,
                item=item,
            )
        )
        return assigned_document_id


class SharedCapturedLinkRepository:
    def __init__(self, store: SharedCapturedDocumentStore) -> None:
        self.store = store

    @property
    def items(self) -> list[CapturedLodgingLink]:
        return [document.item for document in self.store.documents]

    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        for item in items:
            self.store.add_document(item)
        return len(items)

    def find_duplicate(
        self,
        urls: Sequence[str],
        *,
        source_type: str,
        trip_id: str | None = None,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
    ) -> CapturedLodgingLink | None:
        candidate_keys = set(build_lodging_lookup_keys(*urls))
        if not candidate_keys:
            return None

        matches = [
            document.item
            for document in self.store.documents
            if _matches_captured_source(
                document.item,
                source_type=source_type,
                trip_id=trip_id,
                group_id=group_id,
                room_id=room_id,
                user_id=user_id,
            )
            and candidate_keys.intersection(
                build_lodging_lookup_keys(
                    document.item.url,
                    document.item.resolved_url,
                )
            )
        ]
        if not matches:
            return None

        return min(
            matches,
            key=lambda item: (len(item.url), -item.captured_at.timestamp()),
        )


class SharedMapEnrichmentRepository:
    def __init__(self, store: SharedCapturedDocumentStore) -> None:
        self.store = store
        self.pending_limits: list[int | None] = []
        self.all_limits: list[int | None] = []
        self.pending_source_scopes: list[SourceScope | None] = []
        self.all_source_scopes: list[SourceScope | None] = []
        self.resolved: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: SourceScope | None = None,
    ):
        self.pending_limits.append(limit)
        self.pending_source_scopes.append(source_scope)
        return _select_map_candidates(
            self.store.documents,
            limit=limit,
            source_scope=source_scope,
            include_all=False,
        )

    def find_all(
        self,
        limit: int | None = None,
        source_scope: SourceScope | None = None,
    ):
        self.all_limits.append(limit)
        self.all_source_scopes.append(source_scope)
        return _select_map_candidates(
            self.store.documents,
            limit=limit,
            source_scope=source_scope,
            include_all=True,
        )

    def find_failed(
        self,
        limit: int,
        source_scope: SourceScope | None = None,
    ):
        raise NotImplementedError

    def find_by_document_id(self, document_id: str):
        document = _find_stored_document(self.store, document_id)
        if document is None:
            return None
        return MapEnrichmentCandidate(
            document.document_id,
            document.item.url,
            document.item.resolved_url,
        )

    def list_documents(self, limit: int, statuses=None, source_scope=None):
        raise NotImplementedError

    def mark_resolved(self, document_id, enrichment: EnrichedLodgingMap) -> None:
        document = _find_stored_document(self.store, str(document_id))
        assert document is not None
        now = datetime.now(timezone.utc)
        document.item = document.item.model_copy(
            update={
                "resolved_url": enrichment.resolved_url or document.item.resolved_url,
                "resolved_hostname": (
                    enrichment.resolved_hostname or document.item.resolved_hostname
                ),
                "property_name": enrichment.property_name,
                "hero_image_url": enrichment.hero_image_url,
                "line_hero_image_url": enrichment.line_hero_image_url,
                "formatted_address": enrichment.formatted_address,
                "street_address": enrichment.street_address,
                "district": enrichment.district,
                "city": enrichment.city,
                "region": enrichment.region,
                "postal_code": enrichment.postal_code,
                "country_name": enrichment.country_name,
                "country_code": enrichment.country_code,
                "latitude": enrichment.latitude,
                "longitude": enrichment.longitude,
                "place_id": enrichment.place_id,
                "google_maps_url": enrichment.google_maps_url,
                "google_maps_search_url": enrichment.google_maps_search_url,
                "map_source": enrichment.map_source,
                "map_status": "resolved" if enrichment.has_coordinates else "partial",
                "map_error": None,
                "map_retry_count": 0,
                "map_last_attempt_at": now,
                "map_resolved_at": now,
                "property_type": enrichment.property_type,
                "room_count": enrichment.room_count,
                "bedroom_count": enrichment.bedroom_count,
                "bathroom_count": enrichment.bathroom_count,
                "amenities": list(enrichment.amenities),
                "details_source": enrichment.details_source,
                "details_status": "resolved" if enrichment.has_details else "partial",
                "details_error": None,
                "details_retry_count": 0,
                "details_last_attempt_at": now,
                "details_resolved_at": now if enrichment.has_details else None,
                "price_amount": enrichment.price_amount,
                "price_currency": enrichment.price_currency,
                "source_price_amount": enrichment.source_price_amount,
                "source_price_currency": enrichment.source_price_currency,
                "price_exchange_rate": enrichment.price_exchange_rate,
                "price_exchange_rate_source": enrichment.price_exchange_rate_source,
                "pricing_source": enrichment.pricing_source,
                "is_sold_out": enrichment.is_sold_out,
                "availability_source": enrichment.availability_source,
                "pricing_status": "resolved" if enrichment.has_pricing else "partial",
                "pricing_error": None,
                "pricing_retry_count": 0,
                "pricing_last_attempt_at": now,
                "pricing_resolved_at": now if enrichment.has_pricing else None,
            }
        )
        self.resolved.append(str(document_id))

    def mark_failed(self, document_id, error: str) -> None:
        document = _find_stored_document(self.store, str(document_id))
        assert document is not None
        document.item = document.item.model_copy(
            update={
                "map_status": "failed",
                "map_error": error,
                "map_retry_count": document.item.map_retry_count + 1,
                "details_status": "failed",
                "details_error": error,
                "details_retry_count": document.item.details_retry_count + 1,
                "pricing_status": "failed",
                "pricing_error": error,
                "pricing_retry_count": document.item.pricing_retry_count + 1,
            }
        )
        self.failed.append((str(document_id), error))


def _build_payload(
    message_text: str,
    *,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
) -> dict[str, object]:
    return {
        "destination": "Ubot",
        "events": [
            {
                "type": "message",
                "replyToken": "reply-token",
                "mode": "active",
                "timestamp": 1711111111111,
                "source": {
                    "type": source_type,
                    "groupId": group_id,
                    "roomId": room_id,
                    "userId": user_id,
                },
                "message": {
                    "id": "325708",
                    "type": "text",
                    "text": message_text,
                },
            }
        ],
    }


def _build_postback_payload(
    data: str,
    *,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
) -> dict[str, object]:
    return {
        "destination": "Ubot",
        "events": [
            {
                "type": "postback",
                "replyToken": "reply-token",
                "mode": "active",
                "timestamp": 1711111111111,
                "source": {
                    "type": source_type,
                    "groupId": group_id,
                    "roomId": room_id,
                    "userId": user_id,
                },
                "postback": {
                    "data": data,
                },
            }
        ],
    }


def _select_map_candidates(
    documents: Sequence[StoredCapturedDocument],
    *,
    limit: int | None,
    source_scope: SourceScope | None,
    include_all: bool,
) -> list[MapEnrichmentCandidate]:
    candidates = [
        MapEnrichmentCandidate(
            document.document_id,
            document.item.url,
            document.item.resolved_url,
        )
        for document in documents
        if _matches_source_scope(document.item, source_scope)
        and (include_all or _is_pending_map_enrichment(document.item))
    ]
    if limit is None:
        return candidates
    return candidates[:limit]


def _find_stored_document(
    store: SharedCapturedDocumentStore,
    document_id: str,
) -> StoredCapturedDocument | None:
    for document in store.documents:
        if document.document_id == document_id:
            return document
    return None


def _extract_document_number(document_id: str) -> int | None:
    prefix = "doc-"
    if not document_id.startswith(prefix):
        return None
    suffix = document_id[len(prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _is_pending_map_enrichment(item: CapturedLodgingLink) -> bool:
    return item.map_status in {"pending", "failed"}


def _resolve_item_last_updated_at(
    item: CapturedLodgingLink,
) -> datetime | None:
    timestamps = [
        value
        for value in (
            item.captured_at,
            item.map_resolved_at,
            item.details_resolved_at,
            item.pricing_resolved_at,
        )
        if isinstance(value, datetime)
    ]
    if not timestamps:
        return None
    return max(timestamps)


def _matches_source_scope(
    item: CapturedLodgingLink,
    source_scope: SourceScope | None,
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

def _build_captured_link(
    url: str,
    *,
    resolved_url: str | None = None,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
    trip_id: str | None = DEFAULT_TRIP_ID,
    trip_title: str | None = DEFAULT_TRIP_TITLE,
    captured_at: datetime | None = None,
) -> CapturedLodgingLink:
    hostname = (urlsplit(url).hostname or "").lower()
    platform = "booking"
    if "agoda.com" in hostname:
        platform = "agoda"
    elif "airbnb.com" in hostname:
        platform = "airbnb"
    return CapturedLodgingLink(
        platform=platform,
        url=url,
        hostname=hostname,
        resolved_url=resolved_url or url,
        resolved_hostname=(urlsplit(resolved_url or url).hostname or "").lower(),
        message_text=f"請看 {url}",
        source_type=source_type,
        destination="Ubot",
        trip_id=trip_id,
        trip_title=trip_title,
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        message_id="325708",
        event_timestamp_ms=1711111111111,
        event_mode="active",
        captured_at=captured_at or datetime(2026, 3, 30, tzinfo=timezone.utc),
    )


def _matches_captured_source(
    item: CapturedLodgingLink,
    *,
    source_type: str,
    trip_id: str | None,
    group_id: str | None,
    room_id: str | None,
    user_id: str | None,
) -> bool:
    if item.source_type != source_type:
        return False
    if trip_id is not None and item.trip_id != trip_id:
        return False
    if source_type == "group":
        return item.group_id == group_id
    if source_type == "room":
        return item.room_id == room_id
    if source_type == "user":
        return item.user_id == user_id
    return True


def _build_trip(
    *,
    trip_id: str = DEFAULT_TRIP_ID,
    display_token: str = "trip-display-current",
    title: str = DEFAULT_TRIP_TITLE,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
    is_active: bool = True,
) -> LineTrip:
    return LineTrip(
        trip_id=trip_id,
        display_token=display_token,
        title=title,
        source_type=source_type,
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        is_active=is_active,
    )


def _build_trip_scope(
    *,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = None,
    trip_id: str = DEFAULT_TRIP_ID,
    trip_title: str = DEFAULT_TRIP_TITLE,
) -> SourceScope:
    return SourceScope(
        source_type=source_type,
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        trip_id=trip_id,
        trip_title=trip_title,
    )


def _build_decision_summary_result(
    *,
    trip_id: str = DEFAULT_TRIP_ID,
    trip_title: str = DEFAULT_TRIP_TITLE,
    display_token: str = "trip-display-current",
) -> LodgingDecisionSummaryResult:
    return LodgingDecisionSummaryResult(
        request=LodgingDecisionSummaryRequest(
            trip=LodgingDecisionSummaryTrip(
                trip_id=trip_id,
                title=trip_title,
                status="open",
                display_token=display_token,
            ),
            summary=LodgingDecisionSummaryStats(
                total_lodgings=2,
                available_count=1,
                sold_out_count=1,
                unknown_count=0,
            ),
            lodgings=[
                LodgingDecisionSummaryLodging(
                    document_id="doc-1",
                    platform="booking",
                    display_name="Foo Hotel",
                    property_name="Foo Hotel",
                    city="東京",
                    formatted_address="東京都新宿區",
                    price_amount=3200,
                    price_currency="TWD",
                    availability="available",
                    is_sold_out=False,
                    amenities=["wifi", "kitchen"],
                    maps_url="https://maps.google.com/?q=35.1,139.1",
                    target_url="https://www.booking.com/hotel/jp/foo.html",
                ),
                LodgingDecisionSummaryLodging(
                    document_id="doc-2",
                    platform="agoda",
                    display_name="Bar Hotel",
                    property_name="Bar Hotel",
                    city="東京",
                    formatted_address="東京都淺草",
                    price_amount=None,
                    price_currency=None,
                    availability="sold_out",
                    is_sold_out=True,
                    amenities=["onsen"],
                    maps_url="https://maps.google.com/?q=bar",
                    target_url="https://www.agoda.com/bar.html",
                ),
            ],
        ),
        response=LodgingDecisionSummaryResponse(
            top_candidates=[
                LodgingDecisionCandidate(
                    document_id="doc-1",
                    display_name="Foo Hotel",
                    reason="地點與價格資訊完整，適合優先討論。",
                )
            ],
            pros=["地點方便", "價格透明"],
            cons=["缺少實際入住評價"],
            missing_information=["取消政策"],
            discussion_points=["是否優先考慮交通便利性"],
        ),
    )


def _matches_trip_source(
    trip: LineTrip,
    source_scope: SourceScope,
) -> bool:
    if trip.source_type != source_scope.source_type:
        return False
    if source_scope.source_type == "group":
        return trip.group_id == source_scope.group_id
    if source_scope.source_type == "room":
        return trip.room_id == source_scope.room_id
    if source_scope.source_type == "user":
        return trip.user_id == source_scope.user_id
    return False


def _normalize_trip_title(title: str) -> str:
    normalized = title.strip()
    if not normalized:
        raise ValueError("Trip title cannot be empty.")
    return normalized


def test_line_webhook_accepts_common_console_paths() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    app = create_app(
        settings=settings,
        collector=InMemoryCapturedLinkRepository(),
        line_client=fake_line_client,
    )
    client = TestClient(app)

    for webhook_path in ("/webhooks/line", "/callback", "/webhook"):
        payload = _build_payload("/ping")
        body = json.dumps(payload).encode("utf-8")
        signature = generate_signature(settings.line_channel_secret, body)

        response = client.post(
            webhook_path,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Line-Signature": signature,
            },
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True, "captured": 0}

    assert fake_line_client.calls == [
        ("reply-token", "pong"),
        ("reply-token", "pong"),
        ("reply-token", "pong"),
    ]


def test_line_webhook_captures_links_and_replies() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    app = create_app(
        settings=settings,
        collector=repository,
        line_client=fake_line_client,
        lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
    )
    client = TestClient(app)

    payload = _build_payload(
        (
            "候選住宿有 "
            "https://www.booking.com/hotel/jp/foo.html "
            "和 https://www.agoda.com/zh-tw/bar-hotel/hotel/tokyo-jp.html "
            "還有 https://example.com/ignore"
        )
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 2}
    assert [item.platform for item in repository.items] == ["booking", "agoda"]
    assert repository.items[0].resolved_url == repository.items[0].url
    assert repository.items[1].resolved_url == repository.items[1].url
    assert all(item.map_status == "pending" for item in repository.items)
    assert all(item.map_retry_count == 0 for item in repository.items)
    assert all(item.google_maps_url is None for item in repository.items)
    assert all(item.group_id == "Cgroup123" for item in repository.items)
    assert fake_line_client.calls == [
        ("reply-token", "已收到 2 筆住宿連結，會整理到目前旅次。")
    ]


def test_line_webhook_does_not_auto_sync_duplicate_links() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    store = SharedCapturedDocumentStore()
    store.add_document(
        _build_captured_link("https://www.booking.com/hotel/jp/foo.html"),
        document_id="doc-1",
    )
    repository = SharedCapturedLinkRepository(store)
    map_enrichment_repository = SharedMapEnrichmentRepository(store)
    map_enrichment_service = FakeMapEnrichmentService(
        {"https://www.booking.com/hotel/jp/foo.html": None}
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            map_enrichment_repository=map_enrichment_repository,
            map_enrichment_service=map_enrichment_service,
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert len(repository.items) == 1
    assert map_enrichment_repository.pending_limits == []
    assert map_enrichment_service.calls == []
    assert fake_line_client.calls == [
        ("reply-token", "你是不是在找這個\nhttps://www.booking.com/hotel/jp/foo.html")
    ]


def test_line_webhook_control_group_captures_new_links_to_target_group() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    store = SharedCapturedDocumentStore()
    repository = SharedCapturedLinkRepository(store)
    map_enrichment_repository = SharedMapEnrichmentRepository(store)
    url = "https://www.booking.com/hotel/jp/foo.html"
    map_enrichment_service = FakeMapEnrichmentService(
        {
            url: EnrichedLodgingMap(
                property_name="Foo Hotel",
                latitude=35.1,
                longitude=139.1,
                map_source="structured_data_geo",
                google_maps_url="https://maps.google.com/?q=35.1,139.1",
            )
        }
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            map_enrichment_repository=map_enrichment_repository,
            map_enrichment_service=map_enrichment_service,
            trip_group_id="Ctarget123",
        )
    )

    payload = _build_payload(url, group_id="Ccontrol123")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert repository.items[0].group_id == "Ctarget123"
    assert repository.items[0].property_name is None
    assert map_enrichment_repository.pending_source_scopes == []
    assert fake_line_client.calls == [
        ("reply-token", "已收到 1 筆住宿連結，會整理到目前旅次。")
    ]


def test_line_webhook_control_group_duplicate_lookup_uses_target_group_scope() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
            group_id="Ctarget123",
        )
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_group_id="Ctarget123",
        )
    )

    payload = _build_payload(
        "https://www.booking.com/hotel/jp/foo.html",
        group_id="Ccontrol123",
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert len(repository.items) == 1
    assert fake_line_client.calls == [
        ("reply-token", "你是不是在找這個\nhttps://www.booking.com/hotel/jp/foo.html")
    ]


def test_line_webhook_replies_pong_for_ping_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("/ping")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == [("reply-token", "pong")]

def test_line_webhook_replies_help_for_help_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("/help")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == [
        (
            "reply-token",
            (
                "旅次模式操作：\n"
                "1. /建立旅次 東京 2026\n"
                "2. 貼 Booking / Agoda / Airbnb 住宿連結\n"
                "3. /整理 整理目前旅次資料\n"
                "4. /清單 查看目前旅次清單\n"
                "5. /摘要 產生 AI 決策摘要\n"
                "\n"
                "注意：沒有啟用中的旅次時，bot 不會收住宿連結。\n"
                "\n"
                "指令列表：\n"
                "/help：顯示目前支援的指令與說明\n"
                "/ping：回覆 pong\n"
                "/建立旅次：建立新旅次並切換為目前旅次，格式：/建立旅次 <名稱>\n"
                "/切換旅次：切換到既有旅次，格式：/切換旅次 <名稱>\n"
                "/目前旅次：查看目前啟用中的旅次\n"
                "/封存旅次：封存目前旅次並清空 active trip\n"
                "/清單：回傳目前旅次的住宿 preview 與詳情頁連結\n"
                "/摘要：產生目前旅次的 AI 決策摘要\n"
                "/整理：整理目前旅次中尚未補齊的住宿與地圖資料\n"
                "/全部重來：忽略既有整理狀態，重新整理目前旅次中的所有住宿與地圖資料"
            ),
        )
    ]


def test_line_webhook_replies_lodging_decision_summary() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    decision_summary_service = FakeDecisionSummaryService(
        result=_build_decision_summary_result()
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            decision_summary_service=decision_summary_service,
        )
    )

    payload = _build_payload("/摘要")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert decision_summary_service.calls == [DEFAULT_TRIP_ID]
    assert fake_line_client.calls == [
        (
            "reply-token",
            (
                "目前旅次摘要：東京 2026\n"
                "候選住宿 2 筆（可訂 1 / 已售完 1 / 待確認 0）\n"
                "\n"
                "優先候選\n"
                "1. Foo Hotel\n"
                "Booking.com｜TWD 3,200｜可訂｜東京\n"
                "- 地點與價格資訊完整，適合優先討論。\n"
                "\n"
                "優點\n"
                "- 地點方便\n"
                "- 價格透明\n"
                "\n"
                "缺點\n"
                "- 缺少實際入住評價\n"
                "\n"
                "待補資訊\n"
                "- 取消政策\n"
                "\n"
                "討論重點\n"
                "- 是否優先考慮交通便利性"
            ),
        )
    ]


def test_line_webhook_summary_command_requires_active_trip() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    decision_summary_service = FakeDecisionSummaryService(
        result=_build_decision_summary_result()
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            decision_summary_service=decision_summary_service,
            active_trip=False,
        )
    )

    payload = _build_payload("/摘要")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert decision_summary_service.calls == []
    assert fake_line_client.calls == [
        (
            "reply-token",
            "目前沒有啟用中的旅次，請先用 /建立旅次 <名稱> 建立，或用 /切換旅次 <名稱> 切換。",
        )
    ]


def test_line_webhook_summary_command_handles_empty_trip() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    decision_summary_service = FakeDecisionSummaryService(
        error=LodgingDecisionSummaryEmptyTripError("empty trip")
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            decision_summary_service=decision_summary_service,
        )
    )

    payload = _build_payload("/摘要")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert fake_line_client.calls == [
        ("reply-token", "目前旅次還沒有住宿資料可摘要，請先貼住宿連結。")
    ]


def test_line_webhook_summary_command_handles_timeout() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    decision_summary_service = FakeDecisionSummaryService(
        error=LodgingDecisionSummaryTimeoutError("timed out")
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            decision_summary_service=decision_summary_service,
        )
    )

    payload = _build_payload("/摘要")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert fake_line_client.calls == [
        ("reply-token", "目前無法產生住宿摘要，請稍後再試。")
    ]


def test_line_webhook_summary_command_handles_invalid_ai_output() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    decision_summary_service = FakeDecisionSummaryService(
        error=LodgingDecisionSummaryInvalidResponseError("invalid output")
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            decision_summary_service=decision_summary_service,
        )
    )

    payload = _build_payload("/摘要")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert fake_line_client.calls == [
        ("reply-token", "目前無法產生住宿摘要，請稍後再試。")
    ]


def test_line_webhook_supports_trip_management_commands() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    trip_repository = InMemoryTripRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_repository=trip_repository,
            active_trip=False,
        )
    )

    for command in (
        "/建立旅次 東京 2026",
        "/建立旅次 京都 2026",
        "/切換旅次 東京 2026",
        "/目前旅次",
        "/封存旅次",
    ):
        payload = _build_payload(command)
        body = json.dumps(payload).encode("utf-8")
        signature = generate_signature(settings.line_channel_secret, body)
        response = client.post(
            "/webhooks/line",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Line-Signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True, "captured": 0}

    assert trip_repository.get_active_trip(
        SourceScope(source_type="group", group_id="Cgroup123")
    ) is None
    assert fake_line_client.calls == [
        ("reply-token", "已建立並切換到旅次：東京 2026"),
        ("reply-token", "已建立並切換到旅次：京都 2026"),
        ("reply-token", "目前旅次已切換為：東京 2026"),
        (
            "reply-token",
            f"目前旅次：東京 2026\n旅次 ID：trip-1\n狀態：進行中",
        ),
        ("reply-token", "已封存旅次：東京 2026"),
    ]


def test_line_webhook_control_group_commands_manage_target_group_trip_state() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    trip_repository = InMemoryTripRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_repository=trip_repository,
        )
    )

    for command in ("/建立旅次 東京 2026", "/目前旅次"):
        payload = _build_payload(command, group_id="Ccontrol123")
        body = json.dumps(payload).encode("utf-8")
        signature = generate_signature(settings.line_channel_secret, body)
        response = client.post(
            "/webhooks/line",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Line-Signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True, "captured": 0}

    assert (
        trip_repository.get_active_trip(
            SourceScope(source_type="group", group_id="Ccontrol123")
        )
        is None
    )
    target_trip = trip_repository.get_active_trip(
        SourceScope(source_type="group", group_id="Ctarget123")
    )
    assert target_trip is not None
    assert target_trip.title == "東京 2026"
    assert fake_line_client.calls == [
        ("reply-token", "已建立並切換到旅次：東京 2026"),
        (
            "reply-token",
            "目前旅次：東京 2026\n旅次 ID：trip-1\n狀態：進行中",
        ),
    ]


def test_line_webhook_blocks_capture_without_active_trip() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            active_trip=False,
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == [("reply-token", "請先建立或切換旅次，再貼住宿連結。用法：/建立旅次 <名稱> 或 /切換旅次 <名稱>")]


def test_line_webhook_control_group_capture_writes_into_target_group() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    trip_repository = InMemoryTripRepository(
        [
            _build_trip(
                trip_id="trip-control",
                title="Control Trip",
                group_id="Ccontrol123",
            ),
            _build_trip(
                trip_id="trip-target",
                title="Target Trip",
                group_id="Ctarget123",
            ),
        ]
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_repository=trip_repository,
        )
    )

    payload = _build_payload(
        "https://www.booking.com/hotel/jp/foo.html",
        group_id="Ccontrol123",
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert len(repository.items) == 1
    captured = repository.items[0]
    assert captured.group_id == "Ctarget123"
    assert captured.trip_id == "trip-target"
    assert captured.trip_title == "Target Trip"
    assert fake_line_client.calls == [("reply-token", "已收到 1 筆住宿連結，會整理到目前旅次。")]


def test_line_webhook_control_group_capture_requires_target_group_active_trip() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    trip_repository = InMemoryTripRepository(
        [
            _build_trip(
                trip_id="trip-control",
                title="Control Trip",
                group_id="Ccontrol123",
            )
        ]
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_repository=trip_repository,
        )
    )

    payload = _build_payload(
        "https://www.booking.com/hotel/jp/foo.html",
        group_id="Ccontrol123",
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == [
        ("reply-token", "請先建立或切換旅次，再貼住宿連結。用法：/建立旅次 <名稱> 或 /切換旅次 <名稱>")
    ]


def test_line_webhook_control_group_capture_falls_back_when_override_is_partial() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    trip_repository = InMemoryTripRepository(
        [
            _build_trip(
                trip_id="trip-control",
                title="Control Trip",
                group_id="Ccontrol123",
            )
        ]
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_repository=trip_repository,
        )
    )

    payload = _build_payload(
        "https://www.booking.com/hotel/jp/foo.html",
        group_id="Ccontrol123",
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert len(repository.items) == 1
    assert repository.items[0].group_id == "Ccontrol123"
    assert repository.items[0].trip_id == "trip-control"
    assert fake_line_client.calls == [
        ("reply-token", "已收到 1 筆住宿連結，會整理到目前旅次。")
    ]


def test_line_webhook_control_group_capture_falls_back_for_unmatched_group() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    trip_repository = InMemoryTripRepository(
        [
            _build_trip(
                trip_id="trip-other",
                title="Other Trip",
                group_id="Cother123",
            )
        ]
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_repository=trip_repository,
        )
    )

    payload = _build_payload(
        "https://www.booking.com/hotel/jp/foo.html",
        group_id="Cother123",
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert len(repository.items) == 1
    assert repository.items[0].group_id == "Cother123"
    assert repository.items[0].trip_id == "trip-other"
    assert fake_line_client.calls == [
        ("reply-token", "已收到 1 筆住宿連結，會整理到目前旅次。")
    ]


def test_line_webhook_control_group_capture_falls_back_for_non_group_source() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_source_type="room",
            trip_group_id=None,
            trip_room_id="Rroom123",
        )
    )

    payload = _build_payload(
        "https://www.booking.com/hotel/jp/foo.html",
        source_type="room",
        group_id=None,
        room_id="Rroom123",
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert len(repository.items) == 1
    assert repository.items[0].group_id is None
    assert repository.items[0].room_id == "Rroom123"
    assert repository.items[0].trip_id == DEFAULT_TRIP_ID
    assert fake_line_client.calls == [
        ("reply-token", "已收到 1 筆住宿連結，會整理到目前旅次。")
    ]


def test_line_webhook_replies_trip_preview_for_list_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    display_items = [
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
            captured_at=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        ).model_copy(
            update={
                "property_name": "Foo Hotel",
                "hero_image_url": "https://cdn.example.com/foo.jpg",
                "line_hero_image_url": "https://cdn.example.com/foo.jpg",
                "formatted_address": "東京新宿區",
                "price_amount": 4200,
                "price_currency": "TWD",
                "is_sold_out": False,
            }
        ),
        _build_captured_link(
            "https://www.agoda.com/bar-hotel/hotel/tokyo-jp.html",
            captured_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        ).model_copy(
            update={
                "property_name": "Bar Hotel",
                "formatted_address": "東京淺草",
                "is_sold_out": True,
            }
        ),
    ]
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_display_repository=_build_trip_display_repository(
                display_items,
            ),
        )
    )

    payload = _build_payload("/清單")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == []
    reply_token, messages = _single_message_call(fake_line_client)
    assert reply_token == "reply-token"
    assert len(messages) == 1
    flex = messages[0]
    assert flex["type"] == "flex"
    assert flex["altText"] == "東京 2026：已訂 0 筆，候選 2 筆，請開啟旅次詳情查看完整清單。"
    assert flex["contents"]["type"] == "carousel"
    bubbles = flex["contents"]["contents"]
    assert len(bubbles) == 2
    assert bubbles[0]["hero"]["url"] == "https://cdn.example.com/foo.jpg"
    assert bubbles[0]["body"]["contents"][0]["text"] == "Foo Hotel"
    assert bubbles[0]["body"]["contents"][0]["action"]["uri"] == "https://www.booking.com/hotel/jp/foo.html"
    assert bubbles[1]["body"]["contents"][0]["text"] == "Bar Hotel"
    first_footer = bubbles[0]["footer"]["contents"]
    assert first_footer[0]["action"]["type"] == "postback"
    assert first_footer[0]["action"]["label"] == "已訂這間"
    assert "decision_status=booked" in first_footer[0]["action"]["data"]
    assert first_footer[1]["action"]["uri"] == "http://testserver/trips/trip-display-current"
    assert len(first_footer) == 2
    assert "不考慮這間" not in json.dumps(flex, ensure_ascii=False)


def test_line_webhook_control_group_list_command_reads_target_group_trip() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    display_items = [
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
            group_id="Ctarget123",
            captured_at=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        ).model_copy(
            update={
                "property_name": "Foo Hotel",
                "hero_image_url": "https://cdn.example.com/foo.jpg",
                "line_hero_image_url": "https://cdn.example.com/foo.jpg",
                "formatted_address": "東京新宿區",
                "price_amount": 4200,
                "price_currency": "TWD",
                "is_sold_out": False,
            }
        )
    ]
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_display_repository=_build_trip_display_repository(
                display_items,
            ),
            trip_group_id="Ctarget123",
        )
    )

    payload = _build_payload("/清單", group_id="Ccontrol123")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert fake_line_client.calls == []
    reply_token, messages = _single_message_call(fake_line_client)
    assert reply_token == "reply-token"
    flex = messages[0]
    bubble = flex["contents"]["contents"][0]
    assert bubble["body"]["contents"][0]["text"] == "Foo Hotel"
    assert bubble["footer"]["contents"][0]["action"]["label"] == "已訂這間"
    assert bubble["footer"]["contents"][1]["action"]["uri"] == "http://testserver/trips/trip-display-current"


def test_line_webhook_list_command_works_with_trip_display_repository() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    display_items = [
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
        ).model_copy(
            update={
                "property_name": "Foo Hotel",
                "hero_image_url": "https://cdn.example.com/foo.jpg",
                "line_hero_image_url": "https://cdn.example.com/foo.jpg",
                "price_amount": 3500,
                "price_currency": "TWD",
                "is_sold_out": False,
            }
        ),
    ]
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_display_repository=_build_trip_display_repository(display_items),
        )
    )

    payload = _build_payload("/清單")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == []
    reply_token, messages = _single_message_call(fake_line_client)
    assert reply_token == "reply-token"
    assert len(messages) == 1
    flex = messages[0]
    assert flex["type"] == "flex"
    assert flex["contents"]["type"] == "carousel"
    bubble = flex["contents"]["contents"][0]
    assert bubble["hero"]["url"] == "https://cdn.example.com/foo.jpg"
    assert bubble["body"]["contents"][0]["action"]["uri"] == "https://www.booking.com/hotel/jp/foo.html"
    assert bubble["footer"]["contents"][0]["action"]["label"] == "已訂這間"
    assert bubble["footer"]["contents"][1]["action"]["uri"] == "http://testserver/trips/trip-display-current"
    assert len(bubble["footer"]["contents"]) == 2
    assert "Foo Hotel" in json.dumps(flex, ensure_ascii=False)


def test_line_webhook_list_command_renders_booked_revert_action() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    display_items = [
        _build_captured_link("https://www.booking.com/hotel/jp/foo.html").model_copy(
            update={
                "property_name": "Foo Hotel",
                "decision_status": "booked",
                "is_sold_out": False,
            }
        ),
    ]
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_display_repository=_build_trip_display_repository(display_items),
        )
    )

    payload = _build_payload("/清單")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    _, messages = _single_message_call(fake_line_client)
    bubble = messages[0]["contents"]["contents"][0]
    assert "已預訂" in json.dumps(bubble, ensure_ascii=False)
    assert bubble["footer"]["contents"][0]["action"]["label"] == "改回候選"
    assert "decision_status=candidate" in bubble["footer"]["contents"][0]["action"]["data"]


def test_line_webhook_lodging_decision_postback_marks_booked() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link("https://www.booking.com/hotel/jp/foo.html").model_copy(
            update={"property_name": "Foo Hotel"}
        )
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_postback_payload(
        "action=lodging_decision&document_id=doc-1&decision_status=booked"
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items[0].decision_status == "booked"
    assert repository.items[0].decision_updated_by_user_id == "Uuser123"
    assert fake_line_client.calls == [("reply-token", "已標記為已預訂：Foo Hotel")]


def test_line_webhook_lodging_decision_postback_reverts_to_candidate() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link("https://www.booking.com/hotel/jp/foo.html").model_copy(
            update={"property_name": "Foo Hotel", "decision_status": "booked"}
        )
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_postback_payload(
        "action=lodging_decision&document_id=doc-1&decision_status=candidate"
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert repository.items[0].decision_status == "candidate"
    assert fake_line_client.calls == [("reply-token", "已改回候選：Foo Hotel")]


def test_line_webhook_lodging_decision_postback_rejects_out_of_scope_document() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
            group_id="Cother123",
        ).model_copy(update={"property_name": "Foo Hotel"})
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_postback_payload(
        "action=lodging_decision&document_id=doc-1&decision_status=booked"
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert repository.items[0].decision_status == "candidate"
    assert fake_line_client.calls == [
        ("reply-token", "找不到這筆住宿，可能已不在目前旅次。")
    ]


def test_line_webhook_list_command_falls_back_to_text_when_flex_reply_fails() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    line_client = FlexFailingLineClient()
    repository = InMemoryCapturedLinkRepository()
    display_items = [
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
        ).model_copy(
            update={
                "property_name": "Foo Hotel",
                "price_amount": 3500,
                "price_currency": "TWD",
                "is_sold_out": False,
            }
        ),
    ]
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_display_repository=_build_trip_display_repository(display_items),
        )
    )

    payload = _build_payload("/清單")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert len(line_client.message_calls) == 1
    assert line_client.calls == [
        (
            "reply-token",
            (
                "目前旅次：東京 2026\n"
                "住宿 1 筆（已訂 0 / 候選 1 / 不考慮 0）\n"
                "1. Foo Hotel\n"
                "Booking.com｜TWD 3,500｜可訂｜候選中\n"
                "\n"
                "旅次詳情：http://testserver/trips/trip-display-current"
            ),
        )
    ]


def test_line_webhook_trip_detail_page_renders_and_filters_candidates() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    repository = InMemoryCapturedLinkRepository()
    display_items = [
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
            captured_at=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        ).model_copy(
            update={
                "property_name": "Foo Hotel",
                "price_amount": 3200,
                "price_currency": "TWD",
                "is_sold_out": False,
                "hero_image_url": "https://cdn.example.com/foo-detail.webp",
                "line_hero_image_url": "https://cdn.example.com/foo-line.jpg",
                "formatted_address": "東京新宿區",
                "google_maps_url": "https://maps.google.com/?q=35.1,139.1",
            }
        ),
        _build_captured_link(
            "https://www.agoda.com/bar-hotel/hotel/tokyo-jp.html",
            captured_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        ).model_copy(
            update={
                "property_name": "Bar Hotel",
                "is_sold_out": True,
            }
        ),
        _build_captured_link(
            "https://www.airbnb.com/rooms/123",
            captured_at=datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc),
        ).model_copy(
            update={
                "property_name": "Dismissed Home",
                "decision_status": "dismissed",
            }
        ),
    ]
    repository.items.extend(display_items)
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_display_repository=_build_trip_display_repository(
                display_items,
            ),
        )
    )

    response = client.get("/trips/trip-display-current")

    assert response.status_code == 200
    assert "Foo Hotel" in response.text
    assert "Bar Hotel" in response.text
    assert "Dismissed Home" not in response.text
    assert "notion" not in response.text.lower()
    assert "東京新宿區" in response.text
    assert "不考慮這間" in response.text
    assert 'class="card-thumbnail"' in response.text
    assert 'src="https://cdn.example.com/foo-detail.webp"' in response.text
    assert 'href="https://www.booking.com/hotel/jp/foo.html"' in response.text
    assert 'class="card-thumbnail-fallback"' in response.text

    filtered = client.get("/trips/trip-display-current", params={"availability": "available"})

    assert filtered.status_code == 200
    assert "Foo Hotel" in filtered.text
    assert "Bar Hotel" not in filtered.text

    dismissed = client.get(
        "/trips/trip-display-current",
        params={"decision_status": "dismissed"},
    )

    assert dismissed.status_code == 200
    assert "Dismissed Home" in dismissed.text
    assert "改回候選" in dismissed.text

    update_response = client.post(
        "/trips/trip-display-current/lodgings/doc-1/decision",
        data={"decision_status": "dismissed"},
        follow_redirects=False,
    )

    assert update_response.status_code == 303
    assert repository.items[0].decision_status == "dismissed"


def test_line_webhook_trip_detail_page_rejects_invalid_token() -> None:
    client = TestClient(
        create_app(
            collector=InMemoryCapturedLinkRepository(),
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            trip_display_repository=_build_trip_display_repository([]),
        )
    )

    response = client.get("/trips/not-a-real-token")

    assert response.status_code == 404
    assert response.json()["detail"] == "Invalid trip display link."


def test_line_webhook_runs_pending_trip_refresh_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    map_enrichment_repository = InMemoryMapEnrichmentRepository(
        pending_items=[
            MapEnrichmentCandidate(
                "doc-1",
                "https://short.example/doc-1",
                "https://www.booking.com/hotel/jp/doc-1.html",
            ),
            MapEnrichmentCandidate(
                "doc-2",
                "https://www.agoda.com/doc-2.html",
            ),
        ]
    )
    map_enrichment_service = FakeMapEnrichmentService(
        {
            "https://www.booking.com/hotel/jp/doc-1.html": EnrichedLodgingMap(
                property_name="Doc 1 Hotel",
                latitude=35.1,
                longitude=139.1,
                map_source="structured_data_geo",
            ),
            "https://www.agoda.com/doc-2.html": EnrichedLodgingMap(
                property_name="Doc 2 Hotel",
                latitude=35.2,
                longitude=139.2,
                map_source="structured_data_geo",
            ),
        }
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            map_enrichment_repository=map_enrichment_repository,
            map_enrichment_service=map_enrichment_service,
        )
    )

    payload = _build_payload("/整理", source_type="group", group_id="Cgroup123")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert map_enrichment_repository.pending_limits == [None]
    assert map_enrichment_repository.all_limits == []
    assert map_enrichment_repository.pending_source_scopes == [_build_trip_scope()]
    assert map_enrichment_service.calls == [
        "https://www.booking.com/hotel/jp/doc-1.html",
        "https://www.agoda.com/doc-2.html",
    ]
    assert map_enrichment_repository.resolved == ["doc-1", "doc-2"]
    assert fake_line_client.calls == [
        ("reply-token", "旅次資料整理完成：處理 2 筆，完整解析 2 筆，部分更新 0 筆，失敗 0 筆。")
    ]


def test_line_webhook_control_group_runs_pending_trip_refresh_for_target_group() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    map_enrichment_repository = InMemoryMapEnrichmentRepository(
        pending_items=[
            MapEnrichmentCandidate(
                "doc-1",
                "https://short.example/doc-1",
                "https://www.booking.com/hotel/jp/doc-1.html",
            ),
            MapEnrichmentCandidate(
                "doc-2",
                "https://www.agoda.com/doc-2.html",
            ),
        ]
    )
    map_enrichment_service = FakeMapEnrichmentService(
        {
            "https://www.booking.com/hotel/jp/doc-1.html": EnrichedLodgingMap(
                property_name="Doc 1 Hotel",
                latitude=35.1,
                longitude=139.1,
                map_source="structured_data_geo",
            ),
            "https://www.agoda.com/doc-2.html": EnrichedLodgingMap(
                property_name="Doc 2 Hotel",
                latitude=35.2,
                longitude=139.2,
                map_source="structured_data_geo",
            ),
        }
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            map_enrichment_repository=map_enrichment_repository,
            map_enrichment_service=map_enrichment_service,
            trip_group_id="Ctarget123",
        )
    )

    payload = _build_payload("/整理", group_id="Ccontrol123")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert map_enrichment_repository.pending_source_scopes == [
        _build_trip_scope(group_id="Ctarget123")
    ]
    assert fake_line_client.calls == [
        ("reply-token", "旅次資料整理完成：處理 2 筆，完整解析 2 筆，部分更新 0 筆，失敗 0 筆。")
    ]


def test_line_webhook_runs_force_trip_refresh_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    map_enrichment_repository = InMemoryMapEnrichmentRepository(
        all_items=[
            MapEnrichmentCandidate(
                "doc-1",
                "https://short.example/doc-1",
                "https://www.booking.com/hotel/jp/doc-1.html",
            ),
            MapEnrichmentCandidate(
                "doc-2",
                "https://www.agoda.com/doc-2.html",
            ),
        ]
    )
    map_enrichment_service = FakeMapEnrichmentService(
        {
            "https://www.booking.com/hotel/jp/doc-1.html": EnrichedLodgingMap(
                property_name="Doc 1 Hotel",
                latitude=35.1,
                longitude=139.1,
                map_source="structured_data_geo",
            ),
            "https://www.agoda.com/doc-2.html": EnrichedLodgingMap(
                property_name="Doc 2 Hotel",
                latitude=35.2,
                longitude=139.2,
                map_source="structured_data_geo",
            ),
        }
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            map_enrichment_repository=map_enrichment_repository,
            map_enrichment_service=map_enrichment_service,
            trip_source_type="room",
            trip_group_id=None,
            trip_room_id="Rroom123",
        )
    )

    payload = _build_payload(
        "/全部重來",
        source_type="room",
        group_id=None,
        room_id="Rroom123",
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert map_enrichment_repository.pending_limits == []
    assert map_enrichment_repository.all_limits == [None]
    assert map_enrichment_repository.all_source_scopes == [
        _build_trip_scope(
            source_type="room",
            group_id=None,
            room_id="Rroom123",
        )
    ]
    assert map_enrichment_service.calls == [
        "https://www.booking.com/hotel/jp/doc-1.html",
        "https://www.agoda.com/doc-2.html",
    ]
    assert map_enrichment_repository.resolved == ["doc-1", "doc-2"]
    assert fake_line_client.calls == [
        ("reply-token", "旅次資料全部重來完成：處理 2 筆，完整解析 2 筆，部分更新 0 筆，失敗 0 筆。")
    ]


def test_line_webhook_control_group_runs_force_trip_refresh_for_target_group() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        line_command_control_source_group_id="Ccontrol123",
        line_command_control_target_group_id="Ctarget123",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    map_enrichment_repository = InMemoryMapEnrichmentRepository(
        all_items=[
            MapEnrichmentCandidate(
                "doc-1",
                "https://short.example/doc-1",
                "https://www.booking.com/hotel/jp/doc-1.html",
            ),
            MapEnrichmentCandidate(
                "doc-2",
                "https://www.agoda.com/doc-2.html",
            ),
        ]
    )
    map_enrichment_service = FakeMapEnrichmentService(
        {
            "https://www.booking.com/hotel/jp/doc-1.html": EnrichedLodgingMap(
                property_name="Doc 1 Hotel",
                latitude=35.1,
                longitude=139.1,
                map_source="structured_data_geo",
            ),
            "https://www.agoda.com/doc-2.html": EnrichedLodgingMap(
                property_name="Doc 2 Hotel",
                latitude=35.2,
                longitude=139.2,
                map_source="structured_data_geo",
            ),
        }
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            map_enrichment_repository=map_enrichment_repository,
            map_enrichment_service=map_enrichment_service,
            trip_group_id="Ctarget123",
        )
    )

    payload = _build_payload("/全部重來", group_id="Ccontrol123")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert map_enrichment_repository.all_source_scopes == [
        _build_trip_scope(group_id="Ctarget123")
    ]
    assert fake_line_client.calls == [
        ("reply-token", "旅次資料全部重來完成：處理 2 筆，完整解析 2 筆，部分更新 0 筆，失敗 0 筆。")
    ]


def test_line_webhook_reports_when_trip_refresh_is_not_configured() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("/整理")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == [("reply-token", "住宿整理功能尚未設定完成。")]


def test_line_webhook_reports_when_trip_display_link_is_not_configured() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("/清單")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == [("reply-token", "旅次顯示頁尚未設定完成。")]


def test_notion_sync_routes_are_not_registered() -> None:
    client = TestClient(
        create_app(
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    response = client.post("/jobs/notion-sync/run")

    assert response.status_code == 404


def test_line_webhook_reports_when_chat_source_cannot_be_identified() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("/整理", source_type="group", group_id=None)
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == [
        ("reply-token", "無法辨識目前聊天室，暫時無法整理旅次資料。")
    ]


def test_line_webhook_rejects_invalid_signature() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
    )
    client = TestClient(
        create_app(
            settings=settings,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    response = client.post(
        "/webhooks/line",
        json=payload,
        headers={"X-Line-Signature": "bad-signature"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid LINE signature."


def test_line_webhook_still_succeeds_when_reply_fails() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=FailingLineClient(),
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert repository.items[0].url == "https://www.booking.com/hotel/jp/foo.html"
    assert repository.items[0].resolved_url == "https://www.booking.com/hotel/jp/foo.html"


def test_line_webhook_ignores_non_lodging_agoda_links() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload(
        (
            "這兩個不要收 "
            "https://www.agoda.com/activities/detail?cid=1 "
            "https://www.agoda.com/travel-guides/japan/tokyo"
        )
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == []


def test_line_webhook_ignores_non_lodging_booking_links() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload(
        "這個不要收 https://www.booking.com/searchresults.zh-tw.html?ss=Tokyo"
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert repository.items == []
    assert fake_line_client.calls == []

def test_line_webhook_resolves_agoda_short_links_before_capture() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    short_url = "https://www.agoda.com/sp/B70FF37xamn"
    resolved_url = (
        "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
        "?pid=redirect"
    )
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=FakeLineClient(),
            lodging_link_service=LodgingLinkService(resolver),
        )
    )

    payload = _build_payload(short_url)
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert repository.items[0].url == short_url
    assert repository.items[0].resolved_url == resolved_url
    assert resolver.calls == [short_url]


def test_line_webhook_resolves_booking_short_links_before_capture() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    short_url = "https://www.booking.com/Share-08PTGo"
    resolved_url = "https://www.booking.com/hotel/jp/hotel-resol-ueno.zh-tw.html"
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    repository = InMemoryCapturedLinkRepository()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=FakeLineClient(),
            lodging_link_service=LodgingLinkService(resolver),
        )
    )

    payload = _build_payload(short_url)
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert repository.items[0].url == short_url
    assert repository.items[0].resolved_url == resolved_url
    assert resolver.calls == [short_url]


def test_line_webhook_replies_saved_short_link_for_duplicate_direct_url() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.extend(
        [
            _build_captured_link(
                "https://www.booking.com/Share-older",
                resolved_url="https://www.booking.com/hotel/jp/foo.html",
                captured_at=datetime(2026, 3, 29, tzinfo=timezone.utc),
            ),
            _build_captured_link(
                "https://www.booking.com/hotel/jp/foo.html",
                captured_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert len(repository.items) == 2
    assert fake_line_client.calls == [
        ("reply-token", "你是不是在找這個\nhttps://www.booking.com/Share-older")
    ]

def test_line_webhook_replies_current_short_link_for_duplicate_resolved_url() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    short_url = "https://www.booking.com/Share-08PTGo"
    resolved_url = "https://www.booking.com/hotel/jp/foo.html"
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(_build_captured_link(resolved_url))
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(resolver),
        )
    )

    payload = _build_payload(short_url)
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert len(repository.items) == 1
    assert resolver.calls == [short_url]
    assert fake_line_client.calls == [
        ("reply-token", f"你是不是在找這個\n{short_url}")
    ]


def test_line_webhook_matches_duplicates_when_saved_resolved_url_has_tracking_query() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link(
            "https://www.agoda.com/sp/B70FF37xamn",
            resolved_url=(
                "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
                "?pid=redirect"
            ),
        )
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload(
        "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
    )
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 0}
    assert len(repository.items) == 1
    assert fake_line_client.calls == [
        ("reply-token", "你是不是在找這個\nhttps://www.agoda.com/sp/B70FF37xamn")
    ]


def test_line_webhook_only_checks_duplicates_within_same_chat() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    repository.items.append(
        _build_captured_link(
            "https://www.booking.com/hotel/jp/foo.html",
            group_id="Cother-group",
        )
    )
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
        )
    )

    payload = _build_payload("https://www.booking.com/hotel/jp/foo.html")
    body = json.dumps(payload).encode("utf-8")
    signature = generate_signature(settings.line_channel_secret, body)

    response = client.post(
        "/webhooks/line",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "captured": 1}
    assert len(repository.items) == 2
    assert fake_line_client.calls == [
        ("reply-token", "已收到 1 筆住宿連結，會整理到目前旅次。")
    ]
