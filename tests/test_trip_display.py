from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from app.models import LineTrip
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


def test_mongo_trip_display_repository_builds_canonical_surface() -> None:
    trip = LineTrip(
        trip_id="trip-1",
        display_token="trip-display-token",
        title="東京 2026",
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
                    "hero_image_url": "https://cdn.example.com/foo.jpg",
                    "line_hero_image_url": "https://cdn.example.com/foo.jpg",
                    "price_amount": 2800,
                    "price_currency": "TWD",
                    "is_sold_out": False,
                    "captured_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
                    "notion_page_url": "https://www.notion.so/legacy-doc-1",
                    "notion_last_synced_at": datetime(2026, 4, 5, tzinfo=timezone.utc),
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
    assert [lodging.display_name for lodging in surface.lodgings] == [
        "Foo Hotel",
        "Bar Hotel",
    ]
    assert surface.generated_at == datetime(2026, 4, 2, tzinfo=timezone.utc)
    summary_payload = surface.to_summary_payload()
    assert summary_payload["summary"]["total_lodgings"] == 2
    assert summary_payload["summary"]["candidate_count"] == 2
    assert "notion_export_url" not in summary_payload["summary"]
    assert summary_payload["lodgings"][0]["display_name"] == "Foo Hotel"
    assert summary_payload["lodgings"][0]["decision_status"] == "candidate"
    assert "notion_page_url" not in summary_payload["lodgings"][0]
    assert summary_payload["lodgings"][0]["hero_image_url"] == "https://cdn.example.com/foo.jpg"
    assert (
        summary_payload["lodgings"][0]["line_hero_image_url"]
        == "https://cdn.example.com/foo.jpg"
    )


def test_mongo_trip_display_repository_filters_without_external_export() -> None:
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


def test_trip_detail_html_renders_trip_log_rows_with_thumbnails_and_controls() -> None:
    surface = _build_surface(
        (
            TripDisplayLodging(
                document_id="doc-1",
                platform="booking",
                url="https://www.booking.com/hotel/jp/foo.html",
                property_name="Foo Hotel",
                formatted_address="東京新宿區",
                google_maps_url="https://maps.example.com/foo",
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

    assert 'class="trip-app"' in html
    assert 'class="trip-sidebar"' in html
    assert "Trip Log" in html
    assert "平台篩選" in html
    assert "快速篩選" in html
    assert "LINE Japan Bot" in html
    assert "width: 240px;" in html
    assert "@media (max-width: 980px)" in html
    assert "@media (max-width: 640px)" in html
    assert 'class="stats-grid"' in html
    assert 'class="stat-cell"' in html
    assert "已訂" in html
    assert "候選" in html
    assert "不考慮" in html
    assert "待確認" in html
    assert 'class="trip-toolbar"' in html
    assert 'class="toolbar-control"' in html
    assert 'class="trip-controls"' in html
    assert 'select name="availability"' in html
    assert 'select name="decision_status"' in html
    assert 'select name="sort"' in html
    assert "套用" in html
    assert "重設" in html
    assert 'class="lodging-row"' in html
    assert 'class="lodging-row-shell"' in html
    assert 'class="lodging-index"' in html
    assert 'class="lodging-thumbnail-frame"' in html
    assert 'class="lodging-tags"' in html
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
    assert "東京新宿區" in html
    assert "https://maps.example.com/foo" in html
    assert "notion" not in html.lower()
    assert "已訂這間" in html
    assert "不考慮這間" in html
    assert "?decision_status=booked" in html
    assert "?availability=unknown" in html


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
