from __future__ import annotations

from typing import cast
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.controllers.repositories.captured_link_repository import CapturedLinkRepository
from app.controllers.repositories.trip_repository import TripRepository
from app.models import LodgingDecisionStatus
from app.trip_display import (
    TripDisplayAvailability,
    TripDisplayDecisionStatus,
    TripDisplayFilters,
    TripDisplayRepository,
    TripDisplaySort,
    build_trip_detail_html,
)

router = APIRouter(tags=["trip-display"])


def _get_trip_repository(request: Request) -> TripRepository | None:
    return cast(TripRepository | None, request.app.state.trip_repository)


def _get_trip_display_repository(request: Request) -> TripDisplayRepository | None:
    return cast(
        TripDisplayRepository | None,
        request.app.state.trip_display_repository,
    )


def _get_captured_link_repository(request: Request) -> CapturedLinkRepository | None:
    return getattr(request.app.state, "captured_link_repository", None)


@router.get(
    "/trips/{display_token}",
    response_class=HTMLResponse,
    name="trip_detail",
)
async def trip_detail(
    request: Request,
    display_token: str,
    platform: str | None = Query(default=None),
    availability: TripDisplayAvailability = Query(default="all"),
    decision_status: TripDisplayDecisionStatus = Query(default="active"),
    sort: TripDisplaySort = Query(default="captured_desc"),
) -> HTMLResponse:
    trip_repository = _get_trip_repository(request)
    trip_display_repository = _get_trip_display_repository(request)
    if trip_repository is None or trip_display_repository is None:
        raise HTTPException(status_code=503, detail="Trip display is not configured.")

    trip = trip_repository.find_trip_by_display_token(display_token)
    if trip is None:
        raise HTTPException(status_code=404, detail="Invalid trip display link.")

    surface = trip_display_repository.build_trip_display(
        trip,
        TripDisplayFilters(
            platform=platform,
            availability=availability,
            decision_status=decision_status,
            sort=sort,
        ),
    )
    return HTMLResponse(
        content=build_trip_detail_html(surface, request_path=request.url.path),
    )


@router.post(
    "/trips/{display_token}/lodgings/{document_id}/decision",
    name="trip_lodging_decision",
)
async def update_trip_lodging_decision(
    request: Request,
    display_token: str,
    document_id: str,
) -> RedirectResponse:
    trip_repository = _get_trip_repository(request)
    captured_link_repository = _get_captured_link_repository(request)
    if trip_repository is None or captured_link_repository is None:
        raise HTTPException(status_code=503, detail="Trip display is not configured.")

    trip = trip_repository.find_trip_by_display_token(display_token)
    if trip is None:
        raise HTTPException(status_code=404, detail="Invalid trip display link.")

    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    decision_status = _parse_decision_status(_first_form_value(form, "decision_status"))
    updated = captured_link_repository.update_decision_status(
        document_id,
        decision_status=decision_status,
        source_type=trip.source_type,
        trip_id=trip.trip_id,
        group_id=trip.group_id,
        room_id=trip.room_id,
        user_id=trip.user_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Lodging was not found.")

    return RedirectResponse(
        url=str(request.url_for("trip_detail", display_token=display_token)),
        status_code=303,
    )


def _parse_decision_status(value: object) -> LodgingDecisionStatus:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"candidate", "booked", "dismissed"}:
            return normalized  # type: ignore[return-value]
    raise HTTPException(status_code=400, detail="Invalid lodging decision status.")


def _first_form_value(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]
