from __future__ import annotations

from datetime import datetime
from typing import Any

from app.controllers.repositories.mongo_trip_repository import MongoTripRepository
from app.models.trip import LineTrip
from app.notion_sync.models import NotionSyncSourceScope


class FakeInsertOneResult:
    def __init__(self, inserted_id: Any) -> None:
        self.inserted_id = inserted_id


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def find_one(self, filter: dict[str, Any], *args: Any, **kwargs: Any):
        matched = [
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in filter.items())
        ]
        sort = kwargs.get("sort") or []
        for field, direction in reversed(sort):
            matched.sort(
                key=lambda item: item.get(field),
                reverse=direction < 0,
            )
        return dict(matched[0]) if matched else None

    def insert_one(self, document: dict[str, Any], *args: Any, **kwargs: Any):
        self.documents.append(dict(document))
        return FakeInsertOneResult(document.get("trip_id"))

    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        for index, document in enumerate(self.documents):
            if all(document.get(key) == value for key, value in filter.items()):
                updated = dict(document)
                updated.update(update.get("$set", {}))
                self.documents[index] = updated
                return


def test_mongo_trip_repository_can_create_switch_and_archive_trips() -> None:
    collection = FakeCollection()
    repository = MongoTripRepository(collection)
    source_scope = NotionSyncSourceScope(source_type="group", group_id="Cgroup123")

    first_trip = repository.create_trip(source_scope, "東京 2026")
    second_trip = repository.create_trip(source_scope, "京都 2026")
    active_trip = repository.get_active_trip(source_scope)
    switched_trip = repository.switch_active_trip(source_scope, "東京 2026")
    archived_trip = repository.archive_active_trip(source_scope)

    assert first_trip.title == "東京 2026"
    assert second_trip.title == "京都 2026"
    assert active_trip is not None
    assert active_trip.title == "京都 2026"
    assert switched_trip is not None
    assert switched_trip.title == "東京 2026"
    assert archived_trip is not None
    assert archived_trip.title == "東京 2026"
    assert archived_trip.status == "archived"
    assert archived_trip.archived_at is not None
    assert repository.get_active_trip(source_scope) is None

    stored_titles = [LineTrip.model_validate(item).title for item in collection.documents]
    assert stored_titles == ["東京 2026", "京都 2026"]
    assert any(
        item.get("title") == "東京 2026"
        and item.get("status") == "archived"
        and isinstance(item.get("archived_at"), datetime)
        for item in collection.documents
    )
