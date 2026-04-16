from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from app.lodging_summary import (
    GeminiDecisionSummaryClient,
    LodgingDecisionSummaryInvalidResponseError,
    LodgingDecisionSummaryService,
    LodgingDecisionSummaryTimeoutError,
)
from app.models import LineTrip
from app.schemas.lodging_summary import LodgingDecisionCandidate, LodgingDecisionSummaryResponse
from app.trip_display import TripDisplayFilters, TripDisplayLodging, TripDisplaySurface


class StaticTripDisplayRepository:
    def __init__(self, surface: TripDisplaySurface) -> None:
        self.surface = surface
        self.calls: list[tuple[str, TripDisplayFilters | None]] = []

    def build_trip_display(
        self,
        trip: LineTrip,
        filters: TripDisplayFilters | None = None,
    ) -> TripDisplaySurface:
        self.calls.append((trip.trip_id, filters))
        return self.surface


class FakeDecisionSummaryProvider:
    def __init__(
        self,
        response: LodgingDecisionSummaryResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    async def generate_summary(self, request) -> LodgingDecisionSummaryResponse:
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_lodging_decision_summary_service_builds_normalized_payload() -> None:
    trip = LineTrip(
        trip_id="trip-1",
        display_token="display-1",
        title="東京 2026",
        source_type="group",
        group_id="Cgroup123",
    )
    surface = _build_surface()
    repository = StaticTripDisplayRepository(surface)
    service = LodgingDecisionSummaryService(
        repository,
        FakeDecisionSummaryProvider(response=_build_summary_response()),
    )

    request = service.build_summary_request(trip)

    assert repository.calls == [("trip-1", TripDisplayFilters())]
    assert request.trip.title == "東京 2026"
    assert request.summary.total_lodgings == 2
    assert request.lodgings[0].display_name == "Foo Hotel"
    assert request.lodgings[0].city == "東京"
    assert request.lodgings[0].amenities == ["wifi", "kitchen"]
    assert request.lodgings[0].availability == "available"
    assert request.lodgings[1].availability == "sold_out"


def test_lodging_decision_summary_service_rejects_unknown_candidate_ids() -> None:
    trip = LineTrip(
        trip_id="trip-1",
        display_token="display-1",
        title="東京 2026",
        source_type="group",
        group_id="Cgroup123",
    )
    service = LodgingDecisionSummaryService(
        StaticTripDisplayRepository(_build_surface()),
        FakeDecisionSummaryProvider(
            response=LodgingDecisionSummaryResponse(
                top_candidates=[
                    LodgingDecisionCandidate(
                        document_id="doc-999",
                        display_name="Ghost Hotel",
                        reason="不存在的文件",
                    )
                ],
                pros=["價格可能不錯"],
                cons=[],
                missing_information=[],
                discussion_points=["先確認真實資料"],
            )
        ),
    )

    with pytest.raises(LodgingDecisionSummaryInvalidResponseError):
        asyncio.run(service.summarize_trip(trip))


def test_gemini_decision_summary_client_parses_structured_output() -> None:
    response_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                _build_summary_response().model_dump(mode="json"),
                                ensure_ascii=False,
                            )
                        }
                    ]
                }
            }
        ]
    }

    client = GeminiDecisionSummaryClient(
        "test-api-key",
        base_url="https://example.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response_payload)
        ),
    )

    result = asyncio.run(client.generate_summary(_build_request_for_client()))

    assert result.top_candidates[0].document_id == "doc-1"
    assert result.pros == ["地點方便", "價格透明"]


def test_gemini_decision_summary_client_retries_retryable_statuses() -> None:
    calls: list[str] = []
    response_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                _build_summary_response().model_dump(mode="json"),
                                ensure_ascii=False,
                            )
                        }
                    ]
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(503, text="temporarily overloaded")
        return httpx.Response(200, json=response_payload)

    client = GeminiDecisionSummaryClient(
        "test-api-key",
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
        max_retries=1,
        retry_backoff_seconds=0,
    )

    result = asyncio.run(client.generate_summary(_build_request_for_client()))

    assert result.top_candidates[0].document_id == "doc-1"
    assert len(calls) == 2


def test_gemini_decision_summary_client_wraps_timeouts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("boom", request=request)

    client = GeminiDecisionSummaryClient(
        "test-api-key",
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )

    with pytest.raises(LodgingDecisionSummaryTimeoutError):
        asyncio.run(client.generate_summary(_build_request_for_client()))


def _build_surface() -> TripDisplaySurface:
    return TripDisplaySurface(
        trip_id="trip-1",
        trip_title="東京 2026",
        trip_status="open",
        display_token="display-1",
        filters=TripDisplayFilters(),
        lodgings=(
            TripDisplayLodging(
                document_id="doc-1",
                platform="booking",
                url="https://www.booking.com/hotel/jp/foo.html",
                resolved_url="https://www.booking.com/hotel/jp/foo.html",
                property_name="Foo Hotel",
                city="東京",
                formatted_address="東京都新宿區",
                price_amount=3200,
                price_currency="TWD",
                is_sold_out=False,
                amenities=("wifi", "kitchen"),
                google_maps_url="https://maps.google.com/?q=35.1,139.1",
                notion_page_url="https://www.notion.so/foo",
                captured_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
            ),
            TripDisplayLodging(
                document_id="doc-2",
                platform="agoda",
                url="https://www.agoda.com/bar.html",
                resolved_url="https://www.agoda.com/bar.html",
                property_name="Bar Hotel",
                city="東京",
                formatted_address="東京都淺草",
                price_amount=None,
                price_currency=None,
                is_sold_out=True,
                amenities=("onsen",),
                google_maps_search_url="https://maps.google.com/?q=bar",
                captured_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            ),
        ),
        total_lodgings=2,
        available_count=1,
        sold_out_count=1,
        unknown_count=0,
    )


def _build_summary_response() -> LodgingDecisionSummaryResponse:
    return LodgingDecisionSummaryResponse(
        top_candidates=[
            LodgingDecisionCandidate(
                document_id="doc-1",
                display_name="Foo Hotel",
                reason="地點與價格資訊完整，適合優先討論。",
            )
        ],
        pros=["地點方便", "價格透明"],
        cons=["缺少實際入住評價"],
        missing_information=["取消政策"],
        discussion_points=["是否優先考慮交通便利性"],
    )


def _build_request_for_client():
    service = LodgingDecisionSummaryService(
        StaticTripDisplayRepository(_build_surface()),
        FakeDecisionSummaryProvider(response=_build_summary_response()),
    )
    trip = LineTrip(
        trip_id="trip-1",
        display_token="display-1",
        title="東京 2026",
        source_type="group",
        group_id="Cgroup123",
    )
    return service.build_summary_request(trip)
