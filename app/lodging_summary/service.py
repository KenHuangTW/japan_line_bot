from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models import LineTrip
from app.schemas.lodging_summary import (
    LodgingDecisionSummaryLodging,
    LodgingDecisionSummaryRequest,
    LodgingDecisionSummaryResponse,
    LodgingDecisionSummaryStats,
    LodgingDecisionSummaryTrip,
)
from app.trip_display import TripDisplayFilters, TripDisplayRepository, TripDisplaySurface

from app.lodging_summary.errors import (
    LodgingDecisionSummaryConfigurationError,
    LodgingDecisionSummaryEmptyTripError,
    LodgingDecisionSummaryInvalidResponseError,
)


class DecisionSummaryProvider(Protocol):
    async def generate_summary(
        self,
        request: LodgingDecisionSummaryRequest,
    ) -> LodgingDecisionSummaryResponse: ...


class DecisionSummaryService(Protocol):
    async def summarize_trip(
        self,
        trip: LineTrip,
    ) -> "LodgingDecisionSummaryResult": ...


@dataclass(frozen=True)
class LodgingDecisionSummaryResult:
    request: LodgingDecisionSummaryRequest
    response: LodgingDecisionSummaryResponse


class LodgingDecisionSummaryService:
    def __init__(
        self,
        trip_display_repository: TripDisplayRepository | None,
        provider: DecisionSummaryProvider | None,
    ) -> None:
        self.trip_display_repository = trip_display_repository
        self.provider = provider

    def build_summary_request(
        self,
        trip: LineTrip,
    ) -> LodgingDecisionSummaryRequest:
        if self.trip_display_repository is None:
            raise LodgingDecisionSummaryConfigurationError(
                "Trip display repository is required for lodging summaries."
            )

        surface = self.trip_display_repository.build_trip_display(
            trip,
            TripDisplayFilters(),
        )
        return _build_summary_request(surface)

    async def summarize_trip(
        self,
        trip: LineTrip,
    ) -> LodgingDecisionSummaryResult:
        if self.provider is None:
            raise LodgingDecisionSummaryConfigurationError(
                "Decision summary provider is not configured."
            )

        request = self.build_summary_request(trip)
        if not request.lodgings:
            raise LodgingDecisionSummaryEmptyTripError(
                "The active trip does not contain any lodging records."
            )

        response = await self.provider.generate_summary(request)
        _validate_candidate_references(request, response)
        return LodgingDecisionSummaryResult(
            request=request,
            response=response,
        )


def _build_summary_request(
    surface: TripDisplaySurface,
) -> LodgingDecisionSummaryRequest:
    return LodgingDecisionSummaryRequest(
        trip=LodgingDecisionSummaryTrip(
            trip_id=surface.trip_id,
            title=surface.trip_title,
            status=surface.trip_status,
            display_token=surface.display_token,
        ),
        summary=LodgingDecisionSummaryStats(
            total_lodgings=surface.total_lodgings,
            available_count=surface.available_count,
            sold_out_count=surface.sold_out_count,
            unknown_count=surface.unknown_count,
        ),
        lodgings=[
            LodgingDecisionSummaryLodging(
                document_id=lodging.document_id,
                platform=lodging.platform,
                display_name=lodging.display_name,
                property_name=lodging.property_name,
                city=lodging.city,
                formatted_address=lodging.formatted_address,
                price_amount=lodging.price_amount,
                price_currency=lodging.price_currency,
                availability=lodging.availability_key,
                is_sold_out=lodging.is_sold_out,
                amenities=list(lodging.amenities),
                maps_url=lodging.maps_url,
                target_url=lodging.target_url,
                notion_page_url=lodging.notion_page_url,
                captured_at=lodging.captured_at,
                updated_at=lodging.updated_at,
            )
            for lodging in surface.lodgings
        ],
    )


def _validate_candidate_references(
    request: LodgingDecisionSummaryRequest,
    response: LodgingDecisionSummaryResponse,
) -> None:
    valid_document_ids = {lodging.document_id for lodging in request.lodgings}
    unknown_document_ids = [
        candidate.document_id
        for candidate in response.top_candidates
        if candidate.document_id not in valid_document_ids
    ]
    if unknown_document_ids:
        raise LodgingDecisionSummaryInvalidResponseError(
            "Summary response referenced unknown lodging document ids: "
            + ", ".join(unknown_document_ids)
        )
