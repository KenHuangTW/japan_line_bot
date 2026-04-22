from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from app.models import LineTrip
from app.notion_sync.models import NotionSyncSourceScope
from app.notion_sync.targets import NotionTargetConfig
from app.trip_display import (
    MongoTripDisplayRepository,
    TripDisplayFilters,
    TripDisplayLodging,
    TripDisplaySurface,
    build_trip_detail_html,
)


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
    assert surface.candidate_count == 2
    assert surface.booked_count == 0
    assert surface.dismissed_count == 0
    assert surface.notion_export_url == "https://www.notion.so/public-trip-lodgings"
    assert [lodging.display_name for lodging in surface.lodgings] == [
        "Foo Hotel",
        "Bar Hotel",
    ]
    summary_payload = surface.to_summary_payload()
    assert summary_payload["summary"]["total_lodgings"] == 2
    assert summary_payload["summary"]["candidate_count"] == 2
    assert summary_payload["lodgings"][0]["display_name"] == "Foo Hotel"
    assert summary_payload["lodgings"][0]["decision_status"] == "candidate"
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


def test_mongo_trip_display_repository_filters_decision_status() -> None:
    trip = LineTrip(
        trip_id="trip-3",
        display_token="trip-display-token-3",
        title="大阪 2026",
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
                    "property_name": "Booked Hotel",
                    "decision_status": "booked",
                    "captured_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    "source_type": "group",
                    "group_id": "Cgroup123",
                    "trip_id": "trip-3",
                },
                {
                    "_id": "doc-2",
                    "platform": "agoda",
                    "url": "https://www.agoda.com/bar.html",
                    "property_name": "Candidate Hotel",
                    "captured_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
                    "source_type": "group",
                    "group_id": "Cgroup123",
                    "trip_id": "trip-3",
                },
                {
                    "_id": "doc-3",
                    "platform": "airbnb",
                    "url": "https://www.airbnb.com/rooms/1",
                    "property_name": "Dismissed Home",
                    "decision_status": "dismissed",
                    "captured_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
                    "source_type": "group",
                    "group_id": "Cgroup123",
                    "trip_id": "trip-3",
                },
            ]
        )
    )

    surface = repository.build_trip_display(trip, TripDisplayFilters())

    assert surface.total_lodgings == 3
    assert surface.visible_count == 2
    assert surface.booked_count == 1
    assert surface.candidate_count == 1
    assert surface.dismissed_count == 1
    assert [lodging.display_name for lodging in surface.lodgings] == [
        "Booked Hotel",
        "Candidate Hotel",
    ]

    dismissed = repository.build_trip_display(
        trip,
        TripDisplayFilters(decision_status="dismissed"),
    )

    assert dismissed.visible_count == 1
    assert dismissed.lodgings[0].display_name == "Dismissed Home"


def test_trip_detail_html_renders_thumbnail_and_fallback_cards() -> None:
    surface = _build_surface(
        (
            TripDisplayLodging(
                document_id="doc-1",
                platform="booking",
                url="https://www.booking.com/hotel/jp/foo.html",
                property_name="Foo Hotel",
                hero_image_url="https://cdn.example.com/foo-hero.webp",
                line_hero_image_url="https://cdn.example.com/foo-line.jpg",
                price_amount=3200,
                price_currency="TWD",
                is_sold_out=False,
            ),
            TripDisplayLodging(
                document_id="doc-2",
                platform="agoda",
                url="https://www.agoda.com/bar.html",
                property_name="Bar Hotel",
                line_hero_image_url="https://cdn.example.com/bar-line.jpg",
                is_sold_out=True,
            ),
            TripDisplayLodging(
                document_id="doc-3",
                platform="airbnb",
                url="https://www.airbnb.com/rooms/1",
                property_name="Air Home",
            ),
        )
    )

    html = build_trip_detail_html(surface, request_path="/trips/trip-display-token")

    assert 'class="card-media"' in html
    assert 'class="card-thumbnail"' in html
    assert 'src="https://cdn.example.com/foo-hero.webp"' in html
    assert 'src="https://cdn.example.com/foo-line.jpg"' not in html
    assert 'src="https://cdn.example.com/bar-line.jpg"' in html
    assert 'href="https://www.booking.com/hotel/jp/foo.html"' in html
    assert 'class="card-thumbnail-fallback"' in html
    assert "沒有縮圖" in html
    assert "Airbnb" in html
    assert "Foo Hotel" in html
    assert "Booking.com" in html
    assert "已訂這間" in html


def test_trip_detail_html_escapes_thumbnail_url_and_alt_text() -> None:
    surface = _build_surface(
        (
            TripDisplayLodging(
                document_id="doc-1",
                platform="booking",
                url='https://www.booking.com/hotel/jp/foo.html?ref="x"&q=<tag>',
                property_name='Foo "Hotel" <script>',
                hero_image_url='https://cdn.example.com/foo.jpg?size="lg"&q=<tag>',
            ),
        )
    )

    html = build_trip_detail_html(surface, request_path="/trips/trip-display-token")

    assert (
        'src="https://cdn.example.com/foo.jpg?size=&quot;lg&quot;&amp;q=&lt;tag&gt;"'
        in html
    )
    assert 'alt="Foo &quot;Hotel&quot; &lt;script&gt; 縮圖"' in html
    assert (
        'href="https://www.booking.com/hotel/jp/foo.html?ref=&quot;x&quot;&amp;q=&lt;tag&gt;"'
        in html
    )
    assert 'Foo "Hotel" <script>' not in html


def _build_surface(
    lodgings: tuple[TripDisplayLodging, ...],
) -> TripDisplaySurface:
    return TripDisplaySurface(
        trip_id="trip-1",
        trip_title="東京 2026",
        trip_status="active",
        display_token="trip-display-token",
        filters=TripDisplayFilters(),
        lodgings=lodgings,
        total_lodgings=len(lodgings),
        available_count=sum(1 for lodging in lodgings if lodging.is_sold_out is False),
        sold_out_count=sum(1 for lodging in lodgings if lodging.is_sold_out is True),
        unknown_count=sum(1 for lodging in lodgings if lodging.is_sold_out is None),
        candidate_count=sum(
            1 for lodging in lodgings if lodging.decision_status == "candidate"
        ),
        booked_count=sum(
            1 for lodging in lodgings if lodging.decision_status == "booked"
        ),
        dismissed_count=sum(
            1 for lodging in lodgings if lodging.decision_status == "dismissed"
        ),
        platform_options=tuple(sorted({lodging.platform for lodging in lodgings})),
    )
