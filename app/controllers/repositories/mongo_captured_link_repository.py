from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from app.lodging_links.common import build_equivalent_lodging_url_pattern
from app.models import CapturedLodgingLink, LodgingDecisionStatus


class InsertManyResult(Protocol):
    inserted_ids: Sequence[Any]


class UpdateOneResult(Protocol):
    matched_count: int


class MongoCollection(Protocol):
    def insert_many(
        self,
        documents: list[dict[str, Any]],
        ordered: bool = True,
    ) -> InsertManyResult: ...

    def find_one(
        self,
        filter: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None: ...

    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> UpdateOneResult: ...


class MongoCapturedLinkRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        if not items:
            return 0

        documents = [item.model_dump(mode="python") for item in items]
        result = self.collection.insert_many(documents, ordered=True)
        return len(result.inserted_ids)

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
        query = _build_duplicate_query(
            urls=urls,
            source_type=source_type,
            trip_id=trip_id,
            group_id=group_id,
            room_id=room_id,
            user_id=user_id,
        )
        if query is None:
            return None

        duplicate = self.collection.find_one(
            _build_short_link_duplicate_query(query),
            sort=[("captured_at", -1)],
        )
        if duplicate is None:
            duplicate = self.collection.find_one(
                query,
                sort=[("captured_at", -1)],
            )
        if duplicate is None:
            return None
        return CapturedLodgingLink.model_validate(duplicate)

    def update_decision_status(
        self,
        document_id: str,
        *,
        decision_status: LodgingDecisionStatus,
        source_type: str,
        trip_id: str | None = None,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
        updated_by_user_id: str | None = None,
    ) -> CapturedLodgingLink | None:
        document_key = _coerce_document_id(document_id)
        if document_key is None:
            return None

        query = {
            "$and": [
                {"_id": document_key},
                _build_source_scope_query(
                    source_type=source_type,
                    trip_id=trip_id,
                    group_id=group_id,
                    room_id=room_id,
                    user_id=user_id,
                ),
            ]
        }
        now = datetime.now(timezone.utc)
        result = self.collection.update_one(
            query,
            {
                "$set": {
                    "decision_status": decision_status,
                    "decision_updated_at": now,
                    "decision_updated_by_user_id": updated_by_user_id,
                }
            },
        )
        if result.matched_count < 1:
            return None

        updated = self.collection.find_one(query)
        if updated is None:
            return None
        return CapturedLodgingLink.model_validate(updated)


def _build_duplicate_query(
    *,
    urls: Sequence[str],
    source_type: str,
    trip_id: str | None,
    group_id: str | None,
    room_id: str | None,
    user_id: str | None,
) -> dict[str, Any] | None:
    raw_urls = [url.strip() for url in urls if url and url.strip()]
    if not raw_urls:
        return None

    url_clauses: list[dict[str, Any]] = [
        {"url": {"$in": raw_urls}},
        {"resolved_url": {"$in": raw_urls}},
    ]

    for url in raw_urls:
        pattern = build_equivalent_lodging_url_pattern(url)
        if pattern is None:
            continue
        url_clauses.append({"url": {"$regex": pattern}})
        url_clauses.append({"resolved_url": {"$regex": pattern}})

    return {
        "$and": [
            _build_source_scope_query(
                source_type=source_type,
                trip_id=trip_id,
                group_id=group_id,
                room_id=room_id,
                user_id=user_id,
            ),
            {"$or": url_clauses},
        ]
    }


def _build_short_link_duplicate_query(
    base_query: dict[str, Any],
) -> dict[str, Any]:
    return {
        "$and": [
            base_query,
            {"resolved_url": {"$ne": None}},
            {"$expr": {"$ne": ["$url", "$resolved_url"]}},
        ]
    }


def _build_source_scope_query(
    *,
    source_type: str,
    trip_id: str | None,
    group_id: str | None,
    room_id: str | None,
    user_id: str | None,
) -> dict[str, Any]:
    query: dict[str, Any] = {"source_type": source_type}
    if trip_id:
        query["trip_id"] = trip_id

    if source_type == "group":
        query["group_id"] = group_id
    elif source_type == "room":
        query["room_id"] = room_id
    elif source_type == "user":
        query["user_id"] = user_id

    return query


def _coerce_document_id(document_id: str) -> Any | None:
    normalized = str(document_id or "").strip()
    if not normalized:
        return None

    try:
        from bson import ObjectId
    except ModuleNotFoundError:
        return normalized

    try:
        return ObjectId(normalized)
    except Exception:
        return normalized
