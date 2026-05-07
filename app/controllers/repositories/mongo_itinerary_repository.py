from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Protocol, Sequence

from app.models import ItineraryDraft, ItineraryItem, ItinerarySource
from app.source_scope import SourceScope


class InsertOneResult(Protocol):
    inserted_id: Any


class UpdateOneResult(Protocol):
    matched_count: int


class MongoCursor(Protocol):
    def sort(self, key: str, direction: int) -> "MongoCursor": ...

    def __iter__(self): ...


class MongoCollection(Protocol):
    def insert_one(
        self,
        document: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> InsertOneResult: ...

    def find_one(
        self,
        filter: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None: ...

    def find(self, filter: dict[str, Any], *args: Any, **kwargs: Any) -> MongoCursor: ...

    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> UpdateOneResult: ...


class MongoItineraryRepository:
    def __init__(
        self,
        *,
        source_collection: MongoCollection,
        draft_collection: MongoCollection,
        item_collection: MongoCollection,
    ) -> None:
        self.source_collection = source_collection
        self.draft_collection = draft_collection
        self.item_collection = item_collection

    def create_source(self, source: ItinerarySource) -> ItinerarySource:
        self.source_collection.insert_one(source.model_dump(mode="python"))
        return source

    def create_draft(self, draft: ItineraryDraft) -> ItineraryDraft:
        self.draft_collection.insert_one(_to_mongo_document(draft))
        return draft

    def get_latest_pending_draft(
        self,
        source_scope: SourceScope,
    ) -> ItineraryDraft | None:
        document = self.draft_collection.find_one(
            {
                **_build_scope_query(source_scope),
                "status": "pending",
            },
            sort=[("created_at", -1)],
        )
        if document is None:
            return None
        return ItineraryDraft.model_validate(document)

    def mark_draft_applied(self, draft_id: str) -> None:
        self.draft_collection.update_one(
            {"draft_id": draft_id},
            {
                "$set": {
                    "status": "applied",
                    "applied_at": datetime.now(timezone.utc),
                }
            },
        )

    def mark_draft_discarded(self, draft_id: str) -> None:
        self.draft_collection.update_one(
            {"draft_id": draft_id},
            {
                "$set": {
                    "status": "discarded",
                    "discarded_at": datetime.now(timezone.utc),
                }
            },
        )

    def list_items(self, source_scope: SourceScope) -> Sequence[ItineraryItem]:
        documents = self.item_collection.find(_build_scope_query(source_scope)).sort(
            "date",
            1,
        )
        items = [ItineraryItem.model_validate(document) for document in documents]
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    item.date,
                    item.start_time is None,
                    item.start_time,
                    item.title,
                ),
            )
        )

    def upsert_item(self, item: ItineraryItem) -> ItineraryItem:
        now = datetime.now(timezone.utc)
        item = item.model_copy(update={"updated_at": now})
        self.item_collection.update_one(
            {
                "item_id": item.item_id,
                **_build_scope_query(item),
            },
            {"$set": _to_mongo_document(item)},
            upsert=True,
        )
        return item

    def mark_item_cancelled(
        self,
        item_id: str,
        source_scope: SourceScope,
    ) -> ItineraryItem | None:
        now = datetime.now(timezone.utc)
        query = {"item_id": item_id, **_build_scope_query(source_scope)}
        result = self.item_collection.update_one(
            query,
            {"$set": {"status": "cancelled", "updated_at": now}},
        )
        if result.matched_count < 1:
            return None
        document = self.item_collection.find_one(query)
        if document is None:
            return None
        return ItineraryItem.model_validate(document)


def _build_scope_query(scope: Any) -> dict[str, Any]:
    query: dict[str, Any] = {
        "source_type": scope.source_type,
        "trip_id": scope.trip_id,
    }
    if scope.source_type == "group":
        query["group_id"] = scope.group_id
    elif scope.source_type == "room":
        query["room_id"] = scope.room_id
    elif scope.source_type == "user":
        query["user_id"] = scope.user_id
    return query


def _to_mongo_document(model: Any) -> dict[str, Any]:
    return _coerce_mongo_value(model.model_dump(mode="python"))


def _coerce_mongo_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _coerce_mongo_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_coerce_mongo_value(item) for item in value]
    if isinstance(value, tuple):
        return [_coerce_mongo_value(item) for item in value]
    return value
