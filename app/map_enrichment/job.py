from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from app.config import Settings
from app.map_enrichment.models import (
    EnrichedLodgingMap,
    MapEnrichmentCandidate,
    MapEnrichmentDocument,
)
from app.map_enrichment.service import (
    HttpLodgingPageFetcher,
    LodgingMapEnrichmentService,
)


class MongoCollection(Protocol):
    def find(self, *args: Any, **kwargs: Any) -> Any: ...

    def find_one(self, *args: Any, **kwargs: Any) -> Any: ...

    def update_one(self, *args: Any, **kwargs: Any) -> Any: ...


class MapEnrichmentSourceScope(Protocol):
    source_type: str
    group_id: str | None
    room_id: str | None
    user_id: str | None
    trip_id: str | None


class MapEnrichmentRepository(Protocol):
    def find_pending(
        self,
        limit: int | None,
        source_scope: MapEnrichmentSourceScope | None = None,
    ) -> Sequence[MapEnrichmentCandidate]: ...

    def find_all(
        self,
        limit: int | None = None,
        source_scope: MapEnrichmentSourceScope | None = None,
    ) -> Sequence[MapEnrichmentCandidate]: ...

    def find_failed(
        self,
        limit: int,
        source_scope: MapEnrichmentSourceScope | None = None,
    ) -> Sequence[MapEnrichmentCandidate]: ...

    def find_by_document_id(self, document_id: str) -> MapEnrichmentCandidate | None: ...

    def list_documents(
        self,
        limit: int,
        statuses: Sequence[str] | None = None,
    ) -> Sequence[MapEnrichmentDocument]: ...

    def mark_resolved(
        self,
        document_id: Any,
        enrichment: EnrichedLodgingMap,
    ) -> None: ...

    def mark_failed(self, document_id: Any, error: str) -> None: ...


class MongoMapEnrichmentRepository:
    def __init__(self, collection: MongoCollection, max_retry_count: int = 3) -> None:
        self.collection = collection
        self.max_retry_count = max_retry_count

    def find_pending(
        self,
        limit: int | None,
        source_scope: MapEnrichmentSourceScope | None = None,
    ) -> Sequence[MapEnrichmentCandidate]:
        return self._find_candidates(
            {
                "$or": [
                    {"map_status": {"$exists": False}},
                    {"map_status": "pending"},
                    {
                        "$and": [
                            {"map_status": "failed"},
                            {
                                "$or": [
                                    {"map_retry_count": {"$exists": False}},
                                    {
                                        "map_retry_count": {
                                            "$lt": self.max_retry_count
                                        }
                                    },
                                ]
                            },
                        ]
                    },
                ]
            },
            limit=limit,
            source_scope=source_scope,
        )

    def find_all(
        self,
        limit: int | None = None,
        source_scope: MapEnrichmentSourceScope | None = None,
    ) -> Sequence[MapEnrichmentCandidate]:
        return self._find_candidates({}, limit=limit, source_scope=source_scope)

    def find_failed(
        self,
        limit: int,
        source_scope: MapEnrichmentSourceScope | None = None,
    ) -> Sequence[MapEnrichmentCandidate]:
        return self._find_candidates(
            {"map_status": "failed"},
            limit=limit,
            source_scope=source_scope,
        )

    def find_by_document_id(self, document_id: str) -> MapEnrichmentCandidate | None:
        object_id = _coerce_object_id(document_id)
        if object_id is None:
            return None

        document = self.collection.find_one({"_id": object_id})
        if document is None:
            return None

        target_url = document.get("resolved_url") or document.get("url")
        if not target_url:
            return None

        return MapEnrichmentCandidate(
            document_id=document["_id"],
            url=document.get("url", target_url),
            resolved_url=document.get("resolved_url"),
        )

    def _find_candidates(
        self,
        query: dict[str, Any],
        *,
        limit: int | None,
        source_scope: MapEnrichmentSourceScope | None = None,
    ) -> Sequence[MapEnrichmentCandidate]:
        scoped_query = _apply_source_scope_query(query, source_scope)
        cursor = self.collection.find(scoped_query).sort("captured_at", 1)
        if limit is not None:
            cursor = cursor.limit(limit)

        candidates: list[MapEnrichmentCandidate] = []
        for document in cursor:
            target_url = document.get("resolved_url") or document.get("url")
            if not target_url:
                continue
            candidates.append(
                MapEnrichmentCandidate(
                    document_id=document["_id"],
                    url=document.get("url", target_url),
                    resolved_url=document.get("resolved_url"),
                )
            )

        return candidates

    def list_documents(
        self,
        limit: int,
        statuses: Sequence[str] | None = None,
    ) -> Sequence[MapEnrichmentDocument]:
        query: dict[str, Any] = {}
        normalized_statuses = [status for status in (statuses or []) if status]
        if normalized_statuses:
            query["map_status"] = {"$in": normalized_statuses}

        cursor = self.collection.find(query).sort("captured_at", -1).limit(limit)
        documents: list[MapEnrichmentDocument] = []
        for document in cursor:
            documents.append(
                MapEnrichmentDocument(
                    document_id=str(document["_id"]),
                    url=document.get("url", ""),
                    resolved_url=document.get("resolved_url"),
                    map_status=document.get("map_status"),
                    map_source=document.get("map_source"),
                    details_status=document.get("details_status"),
                    details_source=document.get("details_source"),
                    pricing_status=document.get("pricing_status"),
                    pricing_source=document.get("pricing_source"),
                    property_name=document.get("property_name"),
                    hero_image_url=document.get("hero_image_url"),
                    line_hero_image_url=document.get("line_hero_image_url"),
                    formatted_address=document.get("formatted_address"),
                    street_address=document.get("street_address"),
                    district=document.get("district"),
                    city=document.get("city"),
                    region=document.get("region"),
                    postal_code=document.get("postal_code"),
                    country_name=document.get("country_name"),
                    country_code=document.get("country_code"),
                    latitude=document.get("latitude"),
                    longitude=document.get("longitude"),
                    property_type=document.get("property_type"),
                    room_count=document.get("room_count"),
                    bedroom_count=document.get("bedroom_count"),
                    bathroom_count=document.get("bathroom_count"),
                    amenities=tuple(document.get("amenities") or []),
                    price_amount=document.get("price_amount"),
                    price_currency=document.get("price_currency"),
                    source_price_amount=document.get("source_price_amount"),
                    source_price_currency=document.get("source_price_currency"),
                    price_exchange_rate=document.get("price_exchange_rate"),
                    price_exchange_rate_source=document.get(
                        "price_exchange_rate_source"
                    ),
                    is_sold_out=document.get("is_sold_out"),
                    availability_source=document.get("availability_source"),
                    google_maps_url=document.get("google_maps_url"),
                    google_maps_search_url=document.get("google_maps_search_url"),
                    map_error=document.get("map_error"),
                    map_retry_count=document.get("map_retry_count", 0),
                    details_error=document.get("details_error"),
                    details_retry_count=document.get("details_retry_count", 0),
                    pricing_error=document.get("pricing_error"),
                    pricing_retry_count=document.get("pricing_retry_count", 0),
                    captured_at=document.get("captured_at"),
                )
            )

        return documents

    def mark_resolved(
        self,
        document_id: Any,
        enrichment: EnrichedLodgingMap,
    ) -> None:
        now = datetime.now(timezone.utc)
        map_status = "resolved" if enrichment.has_coordinates else "partial"
        details_status = "resolved" if enrichment.has_details else "partial"
        pricing_status = "resolved" if enrichment.has_pricing else "partial"
        self.collection.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "resolved_url": enrichment.resolved_url,
                    "resolved_hostname": enrichment.resolved_hostname,
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
                    "map_status": map_status,
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
                    "details_status": details_status,
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
                    "pricing_status": pricing_status,
                    "pricing_error": None,
                    "pricing_retry_count": 0,
                    "pricing_last_attempt_at": now,
                    "pricing_resolved_at": now if enrichment.has_pricing else None,
                }
            },
        )

    def mark_failed(self, document_id: Any, error: str) -> None:
        self.collection.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "map_status": "failed",
                    "map_error": error[:500],
                    "map_last_attempt_at": datetime.now(timezone.utc),
                    "details_status": "failed",
                    "details_error": error[:500],
                    "details_last_attempt_at": datetime.now(timezone.utc),
                    "pricing_status": "failed",
                    "pricing_error": error[:500],
                    "pricing_last_attempt_at": datetime.now(timezone.utc),
                },
                "$inc": {
                    "map_retry_count": 1,
                    "details_retry_count": 1,
                    "pricing_retry_count": 1,
                },
            },
        )


@dataclass(frozen=True)
class MapEnrichmentSummary:
    processed: int = 0
    resolved: int = 0
    partial: int = 0
    details_resolved: int = 0
    pricing_resolved: int = 0
    failed: int = 0


def _coerce_object_id(document_id: str) -> Any | None:
    try:
        from bson import ObjectId
    except ModuleNotFoundError:
        return document_id

    try:
        return ObjectId(document_id)
    except Exception:
        return None


def _apply_source_scope_query(
    query: dict[str, Any],
    source_scope: MapEnrichmentSourceScope | None,
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
    if source_scope.trip_id:
        source_query["trip_id"] = source_scope.trip_id

    if not query:
        return source_query
    return {"$and": [query, source_query]}


async def run_map_enrichment_job(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    limit: int | None,
    *,
    source_scope: MapEnrichmentSourceScope | None = None,
) -> MapEnrichmentSummary:
    return await _run_map_enrichment_candidates(
        candidates=repository.find_pending(limit, source_scope),
        repository=repository,
        service=service,
    )


async def retry_all_map_enrichment_documents(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    limit: int | None = None,
    *,
    source_scope: MapEnrichmentSourceScope | None = None,
) -> MapEnrichmentSummary:
    return await _run_map_enrichment_candidates(
        candidates=repository.find_all(limit, source_scope),
        repository=repository,
        service=service,
    )


async def retry_all_failed_map_enrichment_documents(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    limit: int,
    *,
    source_scope: MapEnrichmentSourceScope | None = None,
) -> MapEnrichmentSummary:
    return await retry_all_map_enrichment_documents(
        repository=repository,
        service=service,
        limit=limit,
        source_scope=source_scope,
    )


async def _run_map_enrichment_candidates(
    *,
    candidates: Sequence[MapEnrichmentCandidate],
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
) -> MapEnrichmentSummary:
    processed = 0
    resolved = 0
    partial = 0
    details_resolved = 0
    pricing_resolved = 0
    failed = 0

    for candidate in candidates:
        processed += 1
        try:
            enrichment = await service.enrich(candidate.target_url)
        except Exception as error:
            repository.mark_failed(candidate.document_id, str(error))
            failed += 1
            continue

        if enrichment is None:
            repository.mark_failed(
                candidate.document_id,
                "No lodging metadata could be extracted from lodging page.",
            )
            failed += 1
            continue

        repository.mark_resolved(candidate.document_id, enrichment)
        if enrichment.has_coordinates:
            resolved += 1
        else:
            partial += 1
        if enrichment.has_details:
            details_resolved += 1
        if enrichment.has_pricing:
            pricing_resolved += 1

    return MapEnrichmentSummary(
        processed=processed,
        resolved=resolved,
        partial=partial,
        details_resolved=details_resolved,
        pricing_resolved=pricing_resolved,
        failed=failed,
    )


def main() -> int:
    settings = Settings.from_env()

    try:
        from pymongo import MongoClient
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "pymongo is required for the map enrichment job."
        ) from error

    mongo_client = MongoClient(settings.mongo_uri, tz_aware=True)
    collection = mongo_client[settings.mongo_database][settings.mongo_collection]
    repository = MongoMapEnrichmentRepository(
        collection,
        max_retry_count=settings.map_enrichment_max_retry_count,
    )
    service = LodgingMapEnrichmentService(
        HttpLodgingPageFetcher(settings.map_enrichment_request_timeout)
    )

    try:
        summary = asyncio.run(
            run_map_enrichment_job(
                repository=repository,
                service=service,
                limit=settings.map_enrichment_batch_size,
            )
        )
    finally:
        mongo_client.close()

    print(
        "Map enrichment job finished: "
        f"processed={summary.processed} "
        f"resolved={summary.resolved} "
        f"partial={summary.partial} "
        f"details_resolved={summary.details_resolved} "
        f"pricing_resolved={summary.pricing_resolved} "
        f"failed={summary.failed}"
    )
    return 0
