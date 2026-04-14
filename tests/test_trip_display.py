from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from app.models import LineTrip
from app.notion_sync.models import NotionSyncSourceScope
from app.notion_sync.targets import NotionTargetConfig
from app.trip_display import MongoTripDisplayRepository, TripDisplayFilters


class FakeCursor:
    def __init__(self, documents: Sequence[dict[str, Any]]) -> None:
        self.documents = [dict(document) for document in documents]

    def sort(self, key: str, direction: int) -> "FakeCursor":
        self.documents.sort(
            key=lambda item: (item.get(key) is None, item.get(key)),
            reverse=direction < 0,
        )
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self, documents: Sequence[dict[str, Any]]) -> None:
        self.documents = [dict(document) for document in documents]

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor(
            [
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in query.items())
            ]
        )


class InMemoryNotionTargetRepository:
    def __init__(self) -> None:
        self.targets: dict[tuple[str, str, str | None], NotionTargetConfig] = {}

    def find_by_source_scope(
        self,
        source_scope: NotionSyncSourceScope,
    ) -> NotionTargetConfig | None:
        return self.targets.get(
            (source_scope.source_type, source_scope.trip_id or "", source_scope.group_id)
        )

    def save(self, target: NotionTargetConfig) -> None:
        source_scope = target.source_scope
        assert source_scope is not None
        self.targets[
            (source_scope.source_type, source_scope.trip_id or "", source_scope.group_id)
        ] = target


def test_mongo_trip_display_repository_builds_canonical_surface() -> None:
    trip = LineTrip(
        trip_id="trip-1",
        display_token="trip-display-token",
        title="東京 2026",
        source_type="group",
        group_id="Cgroup123",
    )
    target_repository = InMemoryNotionTargetRepository()
    target_repository.save(
        NotionTargetConfig.from_source_scope(
            NotionSyncSourceScope(
                source_type="group",
                group_id="Cgroup123",
                trip_id="trip-1",
                trip_title="東京 2026",
            ),
            database_id="db-current",
            data_source_id="ds-current",
            public_database_url="https://www.notion.so/public-trip-lodgings",
        )
    )
    repository = MongoTripDisplayRepository(
        FakeCollection(
            [
                {
                    "_id": "doc-1",
                    "platform": "booking",
                    "url": "https://www.booking.com/hotel/jp/foo.html",
                    "resolved_url": "https://www.booking.com/hotel/jp/foo.html",
                    "property_name": "Foo Hotel",
                    "hero_image_url": "https://cdn.example.com/foo.jpg",
                    "line_hero_image_url": "https://cdn.example.com/foo.jpg",
                    "price_amount": 2800,
                    "price_currency": "TWD",
                    "is_sold_out": False,
                    "captured_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
                    "source_type": "group",
                    "group_id": "Cgroup123",
                    "trip_id": "trip-1",
                },
                {
                    "_id": "doc-2",
                    "platform": "agoda",
                    "url": "https://www.agoda.com/bar.html",
                    "resolved_url": "https://www.agoda.com/bar.html",
                    "property_name": "Bar Hotel",
                    "is_sold_out": True,
                    "captured_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
                    "source_type": "group",
                    "group_id": "Cgroup123",
                    "trip_id": "trip-1",
                },
            ]
        ),
        target_repository,
    )

    surface = repository.build_trip_display(
        trip,
        TripDisplayFilters(sort="price_asc"),
    )

    assert surface.trip_title == "東京 2026"
    assert surface.display_token == "trip-display-token"
    assert surface.total_lodgings == 2
    assert surface.available_count == 1
    assert surface.sold_out_count == 1
    assert surface.notion_export_url == "https://www.notion.so/public-trip-lodgings"
    assert [lodging.display_name for lodging in surface.lodgings] == [
        "Foo Hotel",
        "Bar Hotel",
    ]
    summary_payload = surface.to_summary_payload()
    assert summary_payload["summary"]["total_lodgings"] == 2
    assert summary_payload["lodgings"][0]["display_name"] == "Foo Hotel"
    assert summary_payload["lodgings"][0]["hero_image_url"] == "https://cdn.example.com/foo.jpg"
    assert (
        summary_payload["lodgings"][0]["line_hero_image_url"]
        == "https://cdn.example.com/foo.jpg"
    )


def test_mongo_trip_display_repository_filters_without_notion_target() -> None:
    trip = LineTrip(
        trip_id="trip-2",
        display_token="trip-display-token-2",
        title="京都 2026",
        source_type="group",
        group_id="Cgroup123",
    )
    repository = MongoTripDisplayRepository(
        FakeCollection(
            [
                {
                    "_id": "doc-1",
                    "platform": "booking",
                    "url": "https://www.booking.com/hotel/jp/foo.html",
                    "resolved_url": "https://www.booking.com/hotel/jp/foo.html",
                    "property_name": "Foo Hotel",
                    "is_sold_out": None,
                    "captured_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
                    "source_type": "group",
                    "group_id": "Cgroup123",
                    "trip_id": "trip-2",
                },
                {
                    "_id": "doc-2",
                    "platform": "airbnb",
                    "url": "https://www.airbnb.com/rooms/1",
                    "resolved_url": "https://www.airbnb.com/rooms/1",
                    "property_name": "Air Home",
                    "is_sold_out": False,
                    "captured_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
                    "source_type": "group",
                    "group_id": "Cgroup123",
                    "trip_id": "trip-2",
                },
            ]
        )
    )

    surface = repository.build_trip_display(
        trip,
        TripDisplayFilters(availability="unknown"),
    )

    assert surface.notion_export_url is None
    assert surface.visible_count == 1
    assert surface.lodgings[0].display_name == "Foo Hotel"
    assert surface.platform_options == ("airbnb", "booking")
