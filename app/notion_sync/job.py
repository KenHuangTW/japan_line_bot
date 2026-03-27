from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from app.notion_sync.models import (
    NotionPageResult,
    NotionSyncCandidate,
    NotionSyncDocument,
    NotionSyncSummary,
)


class MongoCollection(Protocol):
    def find(self, *args: Any, **kwargs: Any) -> Any: ...

    def find_one(self, *args: Any, **kwargs: Any) -> Any: ...

    def update_one(self, *args: Any, **kwargs: Any) -> Any: ...


class NotionSyncService(Protocol):
    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult: ...


class NotionSyncRepository(Protocol):
    def find_pending(self, limit: int) -> Sequence[NotionSyncCandidate]: ...

    def find_all(self, limit: int | None = None) -> Sequence[NotionSyncCandidate]: ...

    def find_by_document_id(self, document_id: str) -> NotionSyncCandidate | None: ...

    def list_documents(
        self,
        limit: int,
        statuses: Sequence[str] | None = None,
    ) -> Sequence[NotionSyncDocument]: ...

    def mark_synced(
        self,
        document_id: Any,
        *,
        page_id: str,
        page_url: str | None,
    ) -> None: ...

    def mark_failed(self, document_id: Any, error: str) -> None: ...


class MongoNotionSyncRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def find_pending(self, limit: int) -> Sequence[NotionSyncCandidate]:
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        last_synced_expr: dict[str, Any] = {
            "$ifNull": ["$notion_last_synced_at", epoch]
        }
        return self._find_candidates(
            {
                "$or": [
                    {"notion_page_id": {"$exists": False}},
                    {"notion_page_id": None},
                    {"notion_sync_status": {"$exists": False}},
                    {"notion_sync_status": "pending"},
                    {"notion_sync_status": "failed"},
                    {
                        "$expr": {
                            "$gt": [{"$ifNull": ["$captured_at", epoch]}, last_synced_expr]
                        }
                    },
                    {
                        "$expr": {
                            "$gt": [
                                {"$ifNull": ["$map_resolved_at", epoch]},
                                last_synced_expr,
                            ]
                        }
                    },
                    {
                        "$expr": {
                            "$gt": [
                                {"$ifNull": ["$details_resolved_at", epoch]},
                                last_synced_expr,
                            ]
                        }
                    },
                    {
                        "$expr": {
                            "$gt": [
                                {"$ifNull": ["$pricing_resolved_at", epoch]},
                                last_synced_expr,
                            ]
                        }
                    },
                ]
            },
            limit=limit,
        )

    def find_all(self, limit: int | None = None) -> Sequence[NotionSyncCandidate]:
        return self._find_candidates({}, limit=limit)

    def find_by_document_id(self, document_id: str) -> NotionSyncCandidate | None:
        object_id = _coerce_object_id(document_id)
        if object_id is None:
            return None

        document = self.collection.find_one({"_id": object_id})
        if document is None:
            return None

        return _build_candidate(document)

    def list_documents(
        self,
        limit: int,
        statuses: Sequence[str] | None = None,
    ) -> Sequence[NotionSyncDocument]:
        query: dict[str, Any] = {}
        normalized_statuses = [status for status in (statuses or []) if status]
        if normalized_statuses:
            clauses: list[dict[str, Any]] = []
            if "pending" in normalized_statuses:
                clauses.append(
                    {
                        "$or": [
                            {"notion_sync_status": {"$exists": False}},
                            {"notion_sync_status": None},
                            {"notion_sync_status": "pending"},
                        ]
                    }
                )
            other_statuses = [status for status in normalized_statuses if status != "pending"]
            if other_statuses:
                clauses.append({"notion_sync_status": {"$in": other_statuses}})

            if len(clauses) == 1:
                query = clauses[0]
            elif clauses:
                query = {"$or": clauses}

        cursor = self.collection.find(query).sort("captured_at", -1).limit(limit)
        documents: list[NotionSyncDocument] = []
        for item in cursor:
            documents.append(
                NotionSyncDocument(
                    document_id=str(item["_id"]),
                    platform=item.get("platform", ""),
                    url=item.get("url", ""),
                    resolved_url=item.get("resolved_url"),
                    property_name=item.get("property_name"),
                    formatted_address=item.get("formatted_address"),
                    city=item.get("city"),
                    country_code=item.get("country_code"),
                    property_type=item.get("property_type"),
                    amenities=tuple(item.get("amenities") or ()),
                    price_amount=item.get("price_amount"),
                    price_currency=item.get("price_currency"),
                    is_sold_out=item.get("is_sold_out"),
                    google_maps_url=item.get("google_maps_url"),
                    google_maps_search_url=item.get("google_maps_search_url"),
                    map_status=item.get("map_status"),
                    details_status=item.get("details_status"),
                    pricing_status=item.get("pricing_status"),
                    notion_page_id=item.get("notion_page_id"),
                    notion_page_url=item.get("notion_page_url"),
                    notion_sync_status=item.get("notion_sync_status") or "pending",
                    notion_sync_error=item.get("notion_sync_error"),
                    notion_sync_retry_count=item.get("notion_sync_retry_count", 0),
                    notion_last_attempt_at=item.get("notion_last_attempt_at"),
                    notion_last_synced_at=item.get("notion_last_synced_at"),
                    captured_at=item.get("captured_at"),
                )
            )

        return documents

    def mark_synced(
        self,
        document_id: Any,
        *,
        page_id: str,
        page_url: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "notion_page_id": page_id,
                    "notion_page_url": page_url,
                    "notion_sync_status": "synced",
                    "notion_sync_error": None,
                    "notion_sync_retry_count": 0,
                    "notion_last_attempt_at": now,
                    "notion_last_synced_at": now,
                }
            },
        )

    def mark_failed(self, document_id: Any, error: str) -> None:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "notion_sync_status": "failed",
                    "notion_sync_error": error,
                    "notion_last_attempt_at": now,
                },
                "$inc": {"notion_sync_retry_count": 1},
            },
        )

    def _find_candidates(
        self,
        query: dict[str, Any],
        *,
        limit: int | None,
    ) -> Sequence[NotionSyncCandidate]:
        cursor = self.collection.find(query).sort("captured_at", 1)
        if limit is not None:
            cursor = cursor.limit(limit)

        candidates: list[NotionSyncCandidate] = []
        for document in cursor:
            candidates.append(_build_candidate(document))
        return candidates


def _build_candidate(document: dict[str, Any]) -> NotionSyncCandidate:
    return NotionSyncCandidate(
        document_id=document["_id"],
        platform=document.get("platform", ""),
        url=document.get("url", ""),
        resolved_url=document.get("resolved_url"),
        property_name=document.get("property_name"),
        formatted_address=document.get("formatted_address"),
        city=document.get("city"),
        country_code=document.get("country_code"),
        property_type=document.get("property_type"),
        amenities=tuple(document.get("amenities") or ()),
        price_amount=document.get("price_amount"),
        price_currency=document.get("price_currency"),
        is_sold_out=document.get("is_sold_out"),
        google_maps_url=document.get("google_maps_url"),
        google_maps_search_url=document.get("google_maps_search_url"),
        map_status=document.get("map_status"),
        details_status=document.get("details_status"),
        pricing_status=document.get("pricing_status"),
        captured_at=document.get("captured_at"),
        notion_page_id=document.get("notion_page_id"),
    )


def _coerce_object_id(document_id: str) -> Any | None:
    try:
        from bson import ObjectId
    except ModuleNotFoundError:
        return document_id

    try:
        return ObjectId(document_id)
    except Exception:
        return None


async def run_notion_sync_job(
    repository: NotionSyncRepository,
    service: NotionSyncService,
    limit: int,
    *,
    force: bool = False,
) -> NotionSyncSummary:
    candidates = repository.find_all(limit) if force else repository.find_pending(limit)
    return await _run_notion_sync_candidates(
        candidates=candidates,
        repository=repository,
        service=service,
    )


async def sync_notion_document(
    repository: NotionSyncRepository,
    service: NotionSyncService,
    document_id: str,
) -> NotionPageResult | None:
    candidate = repository.find_by_document_id(document_id)
    if candidate is None:
        return None

    result = await service.sync_document(candidate)
    repository.mark_synced(
        candidate.document_id,
        page_id=result.page_id,
        page_url=result.page_url,
    )
    return result


async def _run_notion_sync_candidates(
    *,
    candidates: Sequence[NotionSyncCandidate],
    repository: NotionSyncRepository,
    service: NotionSyncService,
) -> NotionSyncSummary:
    summary = NotionSyncSummary()
    for candidate in candidates:
        try:
            result = await service.sync_document(candidate)
        except Exception as error:
            repository.mark_failed(candidate.document_id, str(error))
            summary = NotionSyncSummary(
                processed=summary.processed + 1,
                created=summary.created,
                updated=summary.updated,
                failed=summary.failed + 1,
            )
            continue

        repository.mark_synced(
            candidate.document_id,
            page_id=result.page_id,
            page_url=result.page_url,
        )
        summary = NotionSyncSummary(
            processed=summary.processed + 1,
            created=summary.created + (1 if result.created else 0),
            updated=summary.updated + (0 if result.created else 1),
            failed=summary.failed,
        )

    return summary
