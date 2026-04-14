from __future__ import annotations

from typing import Protocol

from app.models.trip import LineTrip


class TripSourceScope(Protocol):
    source_type: str
    group_id: str | None
    room_id: str | None
    user_id: str | None


class TripRepository(Protocol):
    def create_trip(self, source_scope: TripSourceScope, title: str) -> LineTrip: ...

    def find_open_trip_by_title(
        self,
        source_scope: TripSourceScope,
        title: str,
    ) -> LineTrip | None: ...

    def get_active_trip(self, source_scope: TripSourceScope) -> LineTrip | None: ...

    def find_trip_by_display_token(self, display_token: str) -> LineTrip | None: ...

    def switch_active_trip(
        self,
        source_scope: TripSourceScope,
        title: str,
    ) -> LineTrip | None: ...

    def archive_active_trip(self, source_scope: TripSourceScope) -> LineTrip | None: ...
