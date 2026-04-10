from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from app.notion_sync.models import (
    NotionPageResult,
    NotionSyncCandidate,
    NotionSyncDocument,
    NotionSyncSourceScope,
    NotionSyncSummary,
)
from app.notion_sync.targets import NotionTargetManager, source_scope_from_candidate


class MongoCollection(Protocol):
    def find(self, *args: Any, **kwargs: Any) -> Any: ...

    def find_one(self, *args: Any, **kwargs: Any) -> Any: ...

    def update_one(self, *args: Any, **kwargs: Any) -> Any: ...


class NotionSyncService(Protocol):
    database_id: str
    data_source_id: str

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult: ...


class NotionSyncRepository(Protocol):
    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncCandidate]: ...

    def find_all(
        self,
        limit: int | None = None,
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncCandidate]: ...

    def find_by_document_id(self, document_id: str) -> NotionSyncCandidate | None: ...

    def list_documents(
        self,
        limit: int,
        statuses: Sequence[str] | None = None,
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncDocument]: ...

    def mark_synced(
        self,
        document_id: Any,
        *,
        page_id: str,
        page_url: str | None,
        database_id: str | None,
        data_source_id: str | None,
    ) -> None: ...

    def mark_failed(self, document_id: Any, error: str) -> None: ...


class MongoNotionSyncRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def find_pending(
        self,
        limit: int | None,
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncCandidate]:
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
            source_scope=source_scope,
        )

    def find_all(
        self,
        limit: int | None = None,
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncCandidate]:
        return self._find_candidates({}, limit=limit, source_scope=source_scope)

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
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncDocument]:
        status_query: dict[str, Any] = {}
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
                status_query = clauses[0]
            elif clauses:
                status_query = {"$or": clauses}

        query = _apply_source_scope_query(status_query, source_scope)
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
                    notion_database_id=item.get("notion_database_id"),
                    notion_data_source_id=item.get("notion_data_source_id"),
                    notion_sync_status=item.get("notion_sync_status") or "pending",
                    notion_sync_error=item.get("notion_sync_error"),
                    notion_sync_retry_count=item.get("notion_sync_retry_count", 0),
                    notion_last_attempt_at=item.get("notion_last_attempt_at"),
                    notion_last_synced_at=item.get("notion_last_synced_at"),
                    captured_at=item.get("captured_at"),
                    last_updated_at=_resolve_last_updated_at(item),
                    source_type=item.get("source_type"),
                    group_id=item.get("group_id"),
                    room_id=item.get("room_id"),
                    user_id=item.get("user_id"),
                )
            )

        return documents

    def mark_synced(
        self,
        document_id: Any,
        *,
        page_id: str,
        page_url: str | None,
        database_id: str | None,
        data_source_id: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"_id": document_id},
            {
                "$set": {
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
        source_scope: NotionSyncSourceScope | None = None,
    ) -> Sequence[NotionSyncCandidate]:
        scoped_query = _apply_source_scope_query(query, source_scope)
        cursor = self.collection.find(scoped_query).sort("captured_at", 1)
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
        last_updated_at=_resolve_last_updated_at(document),
        source_type=document.get("source_type"),
        group_id=document.get("group_id"),
        room_id=document.get("room_id"),
        user_id=document.get("user_id"),
        notion_page_id=document.get("notion_page_id"),
        notion_database_id=document.get("notion_database_id"),
        notion_data_source_id=document.get("notion_data_source_id"),
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


def _resolve_last_updated_at(document: dict[str, Any]) -> datetime | None:
    timestamps = [
        value
        for value in (
            document.get("captured_at"),
            document.get("map_resolved_at"),
            document.get("details_resolved_at"),
            document.get("pricing_resolved_at"),
        )
        if isinstance(value, datetime)
    ]
    if not timestamps:
        return None
    return max(timestamps)


def _apply_source_scope_query(
    query: dict[str, Any],
    source_scope: NotionSyncSourceScope | None,
) -> dict[str, Any]:
    if source_scope is None:
        return query

    source_query: dict[str, Any] = {"source_type": source_scope.source_type}
    if source_scope.source_type == "group" and source_scope.group_id:
        source_query["group_id"] = source_scope.group_id
    elif source_scope.source_type == "room" and source_scope.room_id:
        source_query["room_id"] = source_scope.room_id
    elif source_scope.source_type == "user" and source_scope.user_id:
        source_query["user_id"] = source_scope.user_id

    if not query:
        return source_query
    return {"$and": [query, source_query]}


async def run_notion_sync_job(
    repository: NotionSyncRepository,
    service: NotionSyncService | None,
    limit: int | None,
    *,
    force: bool = False,
    source_scope: NotionSyncSourceScope | None = None,
    target_manager: NotionTargetManager | None = None,
) -> NotionSyncSummary:
    candidates = (
        repository.find_all(limit, source_scope)
        if force
        else repository.find_pending(limit, source_scope)
    )
    return await _run_notion_sync_candidates(
        candidates=candidates,
        repository=repository,
        service=service,
        target_manager=target_manager,
    )


async def sync_notion_document(
    repository: NotionSyncRepository,
    service: NotionSyncService | None,
    document_id: str,
    *,
    target_manager: NotionTargetManager | None = None,
) -> NotionPageResult | None:
    candidate = repository.find_by_document_id(document_id)
    if candidate is None:
        return None

    active_service = _resolve_candidate_service(
        candidate=candidate,
        service=service,
        target_manager=target_manager,
    )
    if active_service is None:
        raise RuntimeError("Notion sync is not configured for this source scope.")

    result = await active_service.sync_document(candidate)
    repository.mark_synced(
        candidate.document_id,
        page_id=result.page_id,
        page_url=result.page_url,
        database_id=_get_service_database_id(active_service),
        data_source_id=_get_service_data_source_id(active_service),
    )
    return result


async def _run_notion_sync_candidates(
    *,
    candidates: Sequence[NotionSyncCandidate],
    repository: NotionSyncRepository,
    service: NotionSyncService | None,
    target_manager: NotionTargetManager | None = None,
) -> NotionSyncSummary:
    summary = NotionSyncSummary()
    for candidate in candidates:
        active_service = _resolve_candidate_service(
            candidate=candidate,
            service=service,
            target_manager=target_manager,
        )
        if active_service is None:
            repository.mark_failed(
                candidate.document_id,
                "Notion sync is not configured for this source scope.",
            )
            summary = NotionSyncSummary(
                processed=summary.processed + 1,
                created=summary.created,
                updated=summary.updated,
                failed=summary.failed + 1,
            )
            continue

        try:
            result = await active_service.sync_document(candidate)
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
            database_id=_get_service_database_id(active_service),
            data_source_id=_get_service_data_source_id(active_service),
        )
        summary = NotionSyncSummary(
            processed=summary.processed + 1,
            created=summary.created + (1 if result.created else 0),
            updated=summary.updated + (0 if result.created else 1),
            failed=summary.failed,
        )

    return summary


def _resolve_candidate_service(
    *,
    candidate: NotionSyncCandidate,
    service: NotionSyncService | None,
    target_manager: NotionTargetManager | None,
) -> NotionSyncService | None:
    if target_manager is not None:
        resolved_service = target_manager.resolve_service_for_candidate(candidate)
        if resolved_service is None:
            return None
        return resolved_service.service
    return service


def _get_service_database_id(service: NotionSyncService) -> str | None:
    value = getattr(service, "database_id", "")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _get_service_data_source_id(service: NotionSyncService) -> str | None:
    value = getattr(service, "data_source_id", "")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
