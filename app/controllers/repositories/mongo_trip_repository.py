from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.controllers.repositories.trip_repository import TripSourceScope
from app.models.trip import LineTrip


class InsertOneResult(Protocol):
    inserted_id: Any


class MongoCollection(Protocol):
    def find_one(
        self,
        filter: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None: ...

    def insert_one(
        self,
        document: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> InsertOneResult: ...

    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...


class MongoTripRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def create_trip(self, source_scope: TripSourceScope, title: str) -> LineTrip:
        normalized_title = _normalize_title(title)
        current = self.get_active_trip(source_scope)
        now = datetime.now(timezone.utc)
        if current is not None:
            self.collection.update_one(
                {"trip_id": current.trip_id},
                {"$set": {"is_active": False, "updated_at": now}},
            )

        trip = LineTrip(
            title=normalized_title,
            source_type=source_scope.source_type,
            group_id=source_scope.group_id,
            room_id=source_scope.room_id,
            user_id=source_scope.user_id,
            created_at=now,
            updated_at=now,
        )
        self.collection.insert_one(trip.model_dump(mode="python"))
        return trip

    def find_open_trip_by_title(
        self,
        source_scope: TripSourceScope,
        title: str,
    ) -> LineTrip | None:
        document = self.collection.find_one(
            {
                **_build_source_scope_query(source_scope),
                "status": "open",
                "title": _normalize_title(title),
            }
        )
        return self._hydrate_trip(document)

    def get_active_trip(self, source_scope: TripSourceScope) -> LineTrip | None:
        document = self.collection.find_one(
            {
                **_build_source_scope_query(source_scope),
                "status": "open",
                "is_active": True,
            },
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return self._hydrate_trip(document)

    def find_trip_by_display_token(self, display_token: str) -> LineTrip | None:
        document = self.collection.find_one(
            {"display_token": display_token.strip()},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return self._hydrate_trip(document)

    def switch_active_trip(
        self,
        source_scope: TripSourceScope,
        title: str,
    ) -> LineTrip | None:
        target = self.find_open_trip_by_title(source_scope, title)
        if target is None:
            return None
        if target.is_active:
            return target

        current = self.get_active_trip(source_scope)
        now = datetime.now(timezone.utc)
        if current is not None:
            self.collection.update_one(
                {"trip_id": current.trip_id},
                {"$set": {"is_active": False, "updated_at": now}},
            )
        self.collection.update_one(
            {"trip_id": target.trip_id},
            {"$set": {"is_active": True, "updated_at": now}},
        )
        return target.model_copy(update={"is_active": True, "updated_at": now})

    def archive_active_trip(self, source_scope: TripSourceScope) -> LineTrip | None:
        current = self.get_active_trip(source_scope)
        if current is None:
            return None

        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"trip_id": current.trip_id},
            {
                "$set": {
                    "status": "archived",
                    "is_active": False,
                    "archived_at": now,
                    "updated_at": now,
                }
            },
        )
        return current.model_copy(
            update={
                "status": "archived",
                "is_active": False,
                "archived_at": now,
                "updated_at": now,
            }
        )

    def _hydrate_trip(self, document: dict[str, Any] | None) -> LineTrip | None:
        if document is None:
            return None

        normalized = dict(document)
        display_token = normalized.get("display_token")
        if not isinstance(display_token, str) or not display_token.strip():
            display_token = uuid4().hex
            normalized["display_token"] = display_token
            self.collection.update_one(
                {"trip_id": normalized.get("trip_id")},
                {
                    "$set": {
                        "display_token": display_token,
                        "updated_at": normalized.get("updated_at")
                        or datetime.now(timezone.utc),
                    }
                },
            )

        return LineTrip.model_validate(normalized)


def _build_source_scope_query(source_scope: TripSourceScope) -> dict[str, Any]:
    query: dict[str, Any] = {"source_type": source_scope.source_type}
    if source_scope.source_type == "group":
        query["group_id"] = source_scope.group_id
    elif source_scope.source_type == "room":
        query["room_id"] = source_scope.room_id
    elif source_scope.source_type == "user":
        query["user_id"] = source_scope.user_id
    return query


def _normalize_title(title: str) -> str:
    normalized = title.strip()
    if not normalized:
        raise ValueError("Trip title cannot be empty.")
    return normalized
