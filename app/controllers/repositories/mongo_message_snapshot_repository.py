from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from app.models import LineMessageSnapshot


class UpdateOneResult(Protocol):
    matched_count: int


class MongoCollection(Protocol):
    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> UpdateOneResult: ...

    def find_one(
        self,
        filter: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None: ...


class MongoMessageSnapshotRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def save(self, snapshot: LineMessageSnapshot) -> None:
        document = snapshot.model_dump(mode="python")
        self.collection.update_one(
            {
                "message_id": snapshot.message_id,
                **_build_source_scope_query(
                    source_type=snapshot.source_type,
                    group_id=snapshot.group_id,
                    room_id=snapshot.room_id,
                    user_id=snapshot.user_id,
                ),
            },
            {"$set": document},
            upsert=True,
        )

    def find_text_by_message_id(
        self,
        message_id: str,
        *,
        source_type: str,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
    ) -> LineMessageSnapshot | None:
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            return None

        document = self.collection.find_one(
            {
                "message_id": normalized_message_id,
                **_build_source_scope_query(
                    source_type=source_type,
                    group_id=group_id,
                    room_id=room_id,
                    user_id=user_id,
                ),
                "$or": [
                    {"expires_at": None},
                    {"expires_at": {"$gt": datetime.now(timezone.utc)}},
                ],
            },
            sort=[("created_at", -1)],
        )
        if document is None:
            return None
        return LineMessageSnapshot.model_validate(document)


def _build_source_scope_query(
    *,
    source_type: str,
    group_id: str | None,
    room_id: str | None,
    user_id: str | None,
) -> dict[str, Any]:
    query: dict[str, Any] = {"source_type": source_type}
    if source_type == "group":
        query["group_id"] = group_id
    elif source_type == "room":
        query["room_id"] = room_id
    elif source_type == "user":
        query["user_id"] = user_id
    return query
