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


class MapEnrichmentRepository(Protocol):
    def find_pending(self, limit: int) -> Sequence[MapEnrichmentCandidate]: ...

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

    def find_pending(self, limit: int) -> Sequence[MapEnrichmentCandidate]:
        cursor = (
            self.collection.find(
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
                }
            )
            .sort("captured_at", 1)
            .limit(limit)
        )

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
                    property_name=document.get("property_name"),
                    formatted_address=document.get("formatted_address"),
                    latitude=document.get("latitude"),
                    longitude=document.get("longitude"),
                    google_maps_url=document.get("google_maps_url"),
                    google_maps_search_url=document.get("google_maps_search_url"),
                    map_error=document.get("map_error"),
                    map_retry_count=document.get("map_retry_count", 0),
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
        self.collection.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "resolved_url": enrichment.resolved_url,
                    "resolved_hostname": enrichment.resolved_hostname,
                    "property_name": enrichment.property_name,
                    "formatted_address": enrichment.formatted_address,
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
                },
                "$inc": {
                    "map_retry_count": 1,
                },
            },
        )


@dataclass(frozen=True)
class MapEnrichmentSummary:
    processed: int = 0
    resolved: int = 0
    partial: int = 0
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


async def run_map_enrichment_job(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    limit: int,
) -> MapEnrichmentSummary:
    processed = 0
    resolved = 0
    partial = 0
    failed = 0

    for candidate in repository.find_pending(limit):
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
                "No map metadata could be extracted from lodging page.",
            )
            failed += 1
            continue

        repository.mark_resolved(candidate.document_id, enrichment)
        if enrichment.has_coordinates:
            resolved += 1
        else:
            partial += 1

    return MapEnrichmentSummary(
        processed=processed,
        resolved=resolved,
        partial=partial,
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
        f"failed={summary.failed}"
    )
    return 0
