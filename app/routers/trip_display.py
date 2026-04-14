from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.controllers.repositories.trip_repository import TripRepository
from app.trip_display import (
    TripDisplayAvailability,
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
            sort=sort,
        ),
    )
    return HTMLResponse(
        content=build_trip_detail_html(surface, request_path=request.url.path),
    )
