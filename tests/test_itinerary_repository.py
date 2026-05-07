from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from app.controllers.repositories.mongo_itinerary_repository import (
    MongoItineraryRepository,
)
from app.models import (
    ItineraryDraft,
    ItineraryDraftChange,
    ItineraryItem,
    ItineraryItemPayload,
    ItinerarySource,
)
from app.source_scope import SourceScope


class FakeInsertOneResult:
    def __init__(self, inserted_id: Any) -> None:
        self.inserted_id = inserted_id


class FakeUpdateOneResult:
    def __init__(self, matched_count: int) -> None:
        self.matched_count = matched_count


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = [dict(document) for document in documents]

    def sort(self, key: str, direction: int) -> "FakeCursor":
        self.documents.sort(key=lambda item: item.get(key), reverse=direction < 0)
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def insert_one(self, document: dict[str, Any], *args: Any, **kwargs: Any):
        _reject_unencodable_values(document)
        self.documents.append(dict(document))
        return FakeInsertOneResult(document.get("source_id") or document.get("draft_id"))

    def find_one(self, filter: dict[str, Any], *args: Any, **kwargs: Any):
        matched = [document for document in self.documents if _matches(document, filter)]
        sort = kwargs.get("sort") or []
        for key, direction in reversed(sort):
            matched.sort(key=lambda item: item.get(key), reverse=direction < 0)
        return dict(matched[0]) if matched else None

    def find(self, filter: dict[str, Any], *args: Any, **kwargs: Any):
        return FakeCursor(
            [document for document in self.documents if _matches(document, filter)]
        )

    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> FakeUpdateOneResult:
        for index, document in enumerate(self.documents):
            if _matches(document, filter):
                updated = dict(document)
                set_values = update.get("$set", {})
                _reject_unencodable_values(set_values)
                updated.update(set_values)
                self.documents[index] = updated
                return FakeUpdateOneResult(1)
        if kwargs.get("upsert"):
            set_values = update.get("$set", {})
            _reject_unencodable_values(set_values)
            self.documents.append(dict(set_values))
        return FakeUpdateOneResult(0)


def test_mongo_itinerary_repository_persists_sources_drafts_and_items() -> None:
    source_collection = FakeCollection()
    draft_collection = FakeCollection()
    item_collection = FakeCollection()
    repository = MongoItineraryRepository(
        source_collection=source_collection,
        draft_collection=draft_collection,
        item_collection=item_collection,
    )
    scope = _build_scope()
    source = ItinerarySource(
        source_id="source-1",
        trip_id="trip-current",
        trip_title="名古屋 2026",
        source_type="group",
        group_id="Cgroup",
        source_text="raw",
    )
    draft = ItineraryDraft(
        draft_id="draft-1",
        trip_id="trip-current",
        trip_title="名古屋 2026",
        source_type="group",
        group_id="Cgroup",
        source_id="source-1",
        changes=[
            ItineraryDraftChange(
                action="add",
                proposed_item=_payload("若宮八幡社", date(2026, 6, 1), time(9, 30)),
            )
        ],
    )
    item_late = _item("item-2", "大須觀音", date(2026, 6, 1), time(11, 15))
    item_early = _item("item-1", "若宮八幡社", date(2026, 6, 1), time(9, 30))

    repository.create_source(source)
    repository.create_draft(draft)
    repository.upsert_item(item_late)
    repository.upsert_item(item_early)
    pending = repository.get_latest_pending_draft(scope)
    items = repository.list_items(scope)
    repository.mark_draft_applied("draft-1")
    cancelled = repository.mark_item_cancelled("item-1", scope)

    assert source_collection.documents[0]["source_id"] == "source-1"
    stored_change = draft_collection.documents[0]["changes"][0]["proposed_item"]
    assert stored_change["date"] == "2026-06-01"
    assert stored_change["start_time"] == "09:30:00"
    assert item_collection.documents[0]["date"] == "2026-06-01"
    assert item_collection.documents[0]["start_time"] == "11:15:00"
    assert pending is not None
    assert pending.draft_id == "draft-1"
    assert [item.title for item in items] == ["若宮八幡社", "大須觀音"]
    assert draft_collection.documents[0]["status"] == "applied"
    assert cancelled is not None
    assert cancelled.status == "cancelled"


def test_mongo_itinerary_repository_is_trip_scoped() -> None:
    repository = MongoItineraryRepository(
        source_collection=FakeCollection(),
        draft_collection=FakeCollection(),
        item_collection=FakeCollection(),
    )
    repository.upsert_item(_item("item-1", "A", date(2026, 6, 1), time(9, 0)))
    repository.upsert_item(
        _item(
            "item-2",
            "B",
            date(2026, 6, 1),
            time(10, 0),
            trip_id="trip-other",
        )
    )

    items = repository.list_items(_build_scope())

    assert [item.item_id for item in items] == ["item-1"]


def _payload(title: str, item_date: date, start_time: time) -> ItineraryItemPayload:
    return ItineraryItemPayload(
        date=item_date,
        start_time=start_time,
        title=title,
        location_name=title,
        fingerprint=f"{item_date.isoformat()}-{title}",
    )


def _item(
    item_id: str,
    title: str,
    item_date: date,
    start_time: time,
    *,
    trip_id: str = "trip-current",
) -> ItineraryItem:
    return ItineraryItem(
        item_id=item_id,
        trip_id=trip_id,
        trip_title="名古屋 2026",
        source_type="group",
        group_id="Cgroup",
        date=item_date,
        start_time=start_time,
        title=title,
        location_name=title,
        fingerprint=f"{item_date.isoformat()}-{title}",
    )


def _build_scope() -> SourceScope:
    return SourceScope(
        source_type="group",
        group_id="Cgroup",
        trip_id="trip-current",
        trip_title="名古屋 2026",
    )


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    return all(document.get(key) == value for key, value in query.items())


def _reject_unencodable_values(value: Any) -> None:
    if isinstance(value, datetime):
        return
    if isinstance(value, (date, time)):
        raise TypeError(f"Cannot encode {type(value).__name__}")
    if isinstance(value, dict):
        for item in value.values():
            _reject_unencodable_values(item)
    if isinstance(value, list):
        for item in value:
            _reject_unencodable_values(item)
