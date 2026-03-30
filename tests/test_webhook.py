from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.config import Settings
from app.lodging_links.common import build_lodging_lookup_keys
from app.lodging_links.service import LodgingLinkService
from app.line_security import generate_signature
from app.main import create_app
from app.map_enrichment.models import EnrichedLodgingMap, MapEnrichmentCandidate
from app.models import CapturedLodgingLink
from app.notion_sync.models import (
    NotionPageResult,
    NotionSyncCandidate,
    NotionSyncSourceScope,
)


class FakeLineClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def reply_text(self, reply_token: str, text: str) -> None:
        self.calls.append((reply_token, text))


class FailingLineClient:
    async def reply_text(self, reply_token: str, text: str) -> None:
        raise RuntimeError("simulated LINE reply failure")


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


class InMemoryNotionSyncRepository:
    def __init__(
        self,
        *,
        pending_items: Sequence[NotionSyncCandidate] | None = None,
        all_items: Sequence[NotionSyncCandidate] | None = None,
    ) -> None:
        self.pending_items = list(pending_items or [])
        self.all_items = list(all_items or self.pending_items)
        self.pending_limits: list[int | None] = []
        self.all_limits: list[int | None] = []
        self.pending_source_scopes: list[NotionSyncSourceScope | None] = []
        self.all_source_scopes: list[NotionSyncSourceScope | None] = []
        self.synced: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
    ):
        self.pending_limits.append(limit)
        self.pending_source_scopes.append(source_scope)
        return _filter_notion_candidates(
            self.pending_items,
            limit=limit,
            source_scope=source_scope,
        )

    def find_all(
        self,
        limit: int | None = None,
        source_scope: NotionSyncSourceScope | None = None,
    ):
        self.all_limits.append(limit)
        self.all_source_scopes.append(source_scope)
        return _filter_notion_candidates(
            self.all_items,
            limit=limit,
            source_scope=source_scope,
        )

    def find_by_document_id(self, document_id: str):
        for item in self.all_items:
            if str(item.document_id) == document_id:
                return item
        return None

    def list_documents(self, limit: int, statuses=None):
        raise NotImplementedError

    def mark_synced(
        self,
        document_id,
        *,
        page_id: str,
        page_url: str | None,
        database_id: str | None,
        data_source_id: str | None,
    ) -> None:
        self.synced.append(str(document_id))

    def mark_failed(self, document_id, error: str) -> None:
        self.failed.append((str(document_id), error))


class FakeNotionSyncService:
    def __init__(self, *, is_sync_configured: bool = True) -> None:
        self.database_id = "db-current" if is_sync_configured else ""
        self.data_source_id = "ds-current" if is_sync_configured else ""
        self.database_url = (
            "https://www.notion.so/workspace/Trip-Lodgings-dbcurrent?v=view-current"
            if is_sync_configured
            else ""
        )
        self.public_database_url = (
            "https://www.notion.so/public-trip-lodgings"
            if is_sync_configured
            else ""
        )
        self.calls: list[str] = []
        self.setup_calls: list[str | None] = []
        self.database_url_calls: list[bool] = []

    @property
    def is_sync_configured(self) -> bool:
        return bool(self.data_source_id)

    async def setup_database(self, title: str | None = None):
        self.setup_calls.append(title)
        return None

    async def get_database_url(self, *, prefer_public: bool = True) -> str | None:
        self.database_url_calls.append(prefer_public)
        if prefer_public:
            return self.public_database_url or self.database_url or None
        return self.database_url or self.public_database_url or None

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult:
        document_id = str(candidate.document_id)
        self.calls.append(document_id)
        return NotionPageResult(
            page_id=f"page-{document_id}",
            page_url=f"https://www.notion.so/page-{document_id}",
            created=not (
                candidate.notion_page_id
                and candidate.notion_data_source_id == self.data_source_id
            ),
        )


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
        self.pending_source_scopes: list[NotionSyncSourceScope | None] = []
        self.all_source_scopes: list[NotionSyncSourceScope | None] = []
        self.resolved: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
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
        source_scope: NotionSyncSourceScope | None = None,
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
        source_scope: NotionSyncSourceScope | None = None,
    ):
        raise NotImplementedError

    def find_by_document_id(self, document_id: str):
        raise NotImplementedError

    def list_documents(self, limit: int, statuses=None):
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
        self.pending_source_scopes: list[NotionSyncSourceScope | None] = []
        self.all_source_scopes: list[NotionSyncSourceScope | None] = []
        self.resolved: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
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
        source_scope: NotionSyncSourceScope | None = None,
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
        source_scope: NotionSyncSourceScope | None = None,
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

    def list_documents(self, limit: int, statuses=None):
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


class SharedNotionSyncRepository:
    def __init__(self, store: SharedCapturedDocumentStore) -> None:
        self.store = store
        self.pending_limits: list[int | None] = []
        self.all_limits: list[int | None] = []
        self.pending_source_scopes: list[NotionSyncSourceScope | None] = []
        self.all_source_scopes: list[NotionSyncSourceScope | None] = []
        self.synced: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
    ):
        self.pending_limits.append(limit)
        self.pending_source_scopes.append(source_scope)
        return _select_notion_candidates(
            self.store.documents,
            limit=limit,
            source_scope=source_scope,
            include_all=False,
        )

    def find_all(
        self,
        limit: int | None = None,
        source_scope: NotionSyncSourceScope | None = None,
    ):
        self.all_limits.append(limit)
        self.all_source_scopes.append(source_scope)
        return _select_notion_candidates(
            self.store.documents,
            limit=limit,
            source_scope=source_scope,
            include_all=True,
        )

    def find_by_document_id(self, document_id: str):
        document = _find_stored_document(self.store, document_id)
        if document is None:
            return None
        return _build_shared_notion_candidate(document)

    def list_documents(self, limit: int, statuses=None):
        raise NotImplementedError

    def mark_synced(
        self,
        document_id,
        *,
        page_id: str,
        page_url: str | None,
        database_id: str | None,
        data_source_id: str | None,
    ) -> None:
        document = _find_stored_document(self.store, str(document_id))
        assert document is not None
        now = datetime.now(timezone.utc)
        document.item = document.item.model_copy(
            update={
                "notion_page_id": page_id,
                "notion_page_url": page_url,
                "notion_database_id": database_id,
                "notion_data_source_id": data_source_id,
                "notion_sync_status": "synced",
                "notion_sync_error": None,
                "notion_sync_retry_count": 0,
                "notion_last_attempt_at": now,
                "notion_last_synced_at": now,
            }
        )
        self.synced.append(str(document_id))

    def mark_failed(self, document_id, error: str) -> None:
        document = _find_stored_document(self.store, str(document_id))
        assert document is not None
        document.item = document.item.model_copy(
            update={
                "notion_sync_status": "failed",
                "notion_sync_error": error,
                "notion_sync_retry_count": document.item.notion_sync_retry_count + 1,
                "notion_last_attempt_at": datetime.now(timezone.utc),
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


def _build_notion_candidate(
    document_id: str,
    *,
    notion_page_id: str | None = None,
    notion_data_source_id: str | None = None,
    source_type: str = "group",
    group_id: str | None = "Cgroup123",
    room_id: str | None = None,
    user_id: str | None = "Uuser123",
) -> NotionSyncCandidate:
    return NotionSyncCandidate(
        document_id=document_id,
        platform="booking",
        url=f"https://www.booking.com/hotel/jp/{document_id}.html",
        captured_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source_type=source_type,
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        notion_page_id=notion_page_id,
        notion_data_source_id=notion_data_source_id,
    )


def _filter_notion_candidates(
    items: Sequence[NotionSyncCandidate],
    *,
    limit: int | None,
    source_scope: NotionSyncSourceScope | None,
) -> list[NotionSyncCandidate]:
    filtered = [item for item in items if _matches_source_scope(item, source_scope)]
    if limit is None:
        return filtered
    return filtered[:limit]


def _select_map_candidates(
    documents: Sequence[StoredCapturedDocument],
    *,
    limit: int | None,
    source_scope: NotionSyncSourceScope | None,
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


def _select_notion_candidates(
    documents: Sequence[StoredCapturedDocument],
    *,
    limit: int | None,
    source_scope: NotionSyncSourceScope | None,
    include_all: bool,
) -> list[NotionSyncCandidate]:
    candidates = [
        _build_shared_notion_candidate(document)
        for document in documents
        if _matches_source_scope(document.item, source_scope)
        and (include_all or _is_pending_notion_sync(document.item))
    ]
    if limit is None:
        return candidates
    return candidates[:limit]


def _build_shared_notion_candidate(
    document: StoredCapturedDocument,
) -> NotionSyncCandidate:
    item = document.item
    return NotionSyncCandidate(
        document_id=document.document_id,
        platform=item.platform,
        url=item.url,
        resolved_url=item.resolved_url,
        property_name=item.property_name,
        formatted_address=item.formatted_address,
        city=item.city,
        country_code=item.country_code,
        property_type=item.property_type,
        amenities=tuple(item.amenities),
        price_amount=item.price_amount,
        price_currency=item.price_currency,
        is_sold_out=item.is_sold_out,
        google_maps_url=item.google_maps_url,
        google_maps_search_url=item.google_maps_search_url,
        map_status=item.map_status,
        details_status=item.details_status,
        pricing_status=item.pricing_status,
        captured_at=item.captured_at,
        last_updated_at=_resolve_item_last_updated_at(item),
        source_type=item.source_type,
        group_id=item.group_id,
        room_id=item.room_id,
        user_id=item.user_id,
        notion_page_id=item.notion_page_id,
        notion_database_id=item.notion_database_id,
        notion_data_source_id=item.notion_data_source_id,
    )


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


def _is_pending_notion_sync(item: CapturedLodgingLink) -> bool:
    return item.notion_page_id is None or item.notion_sync_status in {
        "pending",
        "failed",
    }


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
    item: NotionSyncCandidate,
    source_scope: NotionSyncSourceScope | None,
) -> bool:
    if source_scope is None:
        return True
    if item.source_type != source_scope.source_type:
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
    captured_at: datetime | None = None,
) -> CapturedLodgingLink:
    hostname = (urlsplit(url).hostname or "").lower()
    return CapturedLodgingLink(
        platform="agoda" if "agoda.com" in hostname else "booking",
        url=url,
        hostname=hostname,
        resolved_url=resolved_url or url,
        resolved_hostname=(urlsplit(resolved_url or url).hostname or "").lower(),
        message_text=f"請看 {url}",
        source_type=source_type,
        destination="Ubot",
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
    group_id: str | None,
    room_id: str | None,
    user_id: str | None,
) -> bool:
    if item.source_type != source_type:
        return False
    if source_type == "group":
        return item.group_id == group_id
    if source_type == "room":
        return item.room_id == room_id
    if source_type == "user":
        return item.user_id == user_id
    return True


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
        ("reply-token", "已收到 2 筆住宿連結，會自動整理並同步到 Notion。")
    ]


def test_line_webhook_auto_syncs_new_links_to_notion() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    store = SharedCapturedDocumentStore()
    repository = SharedCapturedLinkRepository(store)
    map_enrichment_repository = SharedMapEnrichmentRepository(store)
    notion_repository = SharedNotionSyncRepository(store)
    notion_service = FakeNotionSyncService()
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
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
        )
    )

    payload = _build_payload(url)
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
    assert map_enrichment_repository.pending_limits == [None]
    assert map_enrichment_repository.pending_source_scopes == [
        NotionSyncSourceScope(source_type="group", group_id="Cgroup123")
    ]
    assert map_enrichment_service.calls == [url]
    assert notion_repository.pending_limits == [None]
    assert notion_repository.pending_source_scopes == [
        NotionSyncSourceScope(source_type="group", group_id="Cgroup123")
    ]
    assert notion_repository.synced == ["doc-1"]
    assert notion_service.calls == ["doc-1"]
    assert repository.items[0].property_name == "Foo Hotel"
    assert repository.items[0].map_status == "resolved"
    assert repository.items[0].notion_sync_status == "synced"
    assert repository.items[0].notion_page_id == "page-doc-1"
    assert fake_line_client.calls == [
        ("reply-token", "已收到 1 筆住宿連結，會自動整理並同步到 Notion。")
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
    notion_repository = SharedNotionSyncRepository(store)
    notion_service = FakeNotionSyncService()
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
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
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
    assert notion_repository.pending_limits == []
    assert map_enrichment_service.calls == []
    assert notion_service.calls == []
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
                "目前支援的指令：\n"
                "/help：顯示目前支援的指令與說明\n"
                "/ping：回覆 pong\n"
                "/清單：直接回傳目前 Notion 住宿清單的連結\n"
                "/整理：執行 Notion sync，只整理發出指令的那個聊天室中 pending / 尚未同步完成的資料\n"
                "/全部重來：忽略既有同步狀態，只把發出指令的那個聊天室中的資料強制重新同步到 Notion"
            ),
        )
    ]


def test_line_webhook_replies_notion_link_for_list_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            notion_sync_service=notion_service,
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
    assert notion_service.database_url_calls == [True]
    assert fake_line_client.calls == [("reply-token", "https://www.notion.so/public-trip-lodgings")]


def test_line_webhook_prefers_refreshed_public_link_over_cached_internal_link() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
        notion_database_url="https://www.notion.so/44155b3c938c4e6e8cea913a7927b7b",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            notion_sync_service=notion_service,
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
    assert notion_service.database_url_calls == [True]
    assert settings.notion_public_database_url == "https://www.notion.so/public-trip-lodgings"
    assert fake_line_client.calls == [("reply-token", "https://www.notion.so/public-trip-lodgings")]


def test_line_webhook_runs_pending_notion_sync_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_repository = InMemoryNotionSyncRepository(
        pending_items=[
            _build_notion_candidate("doc-1"),
            _build_notion_candidate("doc-2"),
            _build_notion_candidate("doc-other-group", group_id="Cgroup999"),
        ]
    )
    notion_service = FakeNotionSyncService()
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
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
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
    assert map_enrichment_repository.pending_source_scopes == [
        NotionSyncSourceScope(source_type="group", group_id="Cgroup123")
    ]
    assert map_enrichment_service.calls == [
        "https://www.booking.com/hotel/jp/doc-1.html",
        "https://www.agoda.com/doc-2.html",
    ]
    assert map_enrichment_repository.resolved == ["doc-1", "doc-2"]
    assert notion_repository.pending_limits == [None]
    assert notion_repository.all_limits == []
    assert notion_repository.pending_source_scopes == [
        NotionSyncSourceScope(source_type="group", group_id="Cgroup123")
    ]
    assert notion_service.calls == ["doc-1", "doc-2"]
    assert fake_line_client.calls == [
        ("reply-token", "Notion 整理完成：處理 2 筆，新增 2 筆，更新 0 筆，失敗 0 筆。")
    ]


def test_line_webhook_runs_force_notion_sync_command() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_repository = InMemoryNotionSyncRepository(
        all_items=[
            _build_notion_candidate(
                "doc-1",
                notion_page_id="page-doc-1",
                notion_data_source_id="ds-current",
                source_type="room",
                group_id=None,
                room_id="Rroom123",
            ),
            _build_notion_candidate(
                "doc-2",
                source_type="room",
                group_id=None,
                room_id="Rroom123",
            ),
            _build_notion_candidate(
                "doc-other-room",
                source_type="room",
                group_id=None,
                room_id="Rroom999",
            ),
        ]
    )
    notion_service = FakeNotionSyncService()
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
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
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
        NotionSyncSourceScope(source_type="room", room_id="Rroom123")
    ]
    assert map_enrichment_service.calls == [
        "https://www.booking.com/hotel/jp/doc-1.html",
        "https://www.agoda.com/doc-2.html",
    ]
    assert map_enrichment_repository.resolved == ["doc-1", "doc-2"]
    assert notion_repository.pending_limits == []
    assert notion_repository.all_limits == [None]
    assert notion_repository.all_source_scopes == [
        NotionSyncSourceScope(source_type="room", room_id="Rroom123")
    ]
    assert notion_service.setup_calls == [None]
    assert notion_service.calls == ["doc-1", "doc-2"]
    assert fake_line_client.calls == [
        ("reply-token", "Notion 全部重來完成：處理 2 筆，新增 1 筆，更新 1 筆，失敗 0 筆。")
    ]


def test_line_webhook_reports_when_notion_sync_is_not_configured() -> None:
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
    assert fake_line_client.calls == [("reply-token", "Notion sync 尚未設定完成。")]


def test_line_webhook_reports_when_notion_list_link_is_not_configured() -> None:
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
    assert fake_line_client.calls == [("reply-token", "Notion 清單連結尚未設定完成。")]


def test_line_webhook_reports_when_chat_source_cannot_be_identified() -> None:
    settings = Settings(
        line_channel_secret="super-secret",
        line_channel_access_token="line-token",
    )
    fake_line_client = FakeLineClient()
    repository = InMemoryCapturedLinkRepository()
    notion_repository = InMemoryNotionSyncRepository(
        pending_items=[_build_notion_candidate("doc-1")]
    )
    notion_service = FakeNotionSyncService()
    client = TestClient(
        create_app(
            settings=settings,
            collector=repository,
            line_client=fake_line_client,
            lodging_link_service=LodgingLinkService(FakeLodgingUrlResolver()),
            notion_sync_repository=notion_repository,
            notion_sync_service=notion_service,
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
    assert notion_repository.pending_limits == []
    assert notion_service.calls == []
    assert fake_line_client.calls == [
        ("reply-token", "無法辨識目前聊天室，暫時無法執行 Notion sync。")
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
        ("reply-token", "已收到 1 筆住宿連結，會自動整理並同步到 Notion。")
    ]
