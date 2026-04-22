from __future__ import annotations

from typing import Protocol, Sequence

from app.models import CapturedLodgingLink, LodgingDecisionStatus


class CapturedLinkRepository(Protocol):
    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int: ...

    def find_duplicate(
        self,
        urls: Sequence[str],
        *,
        source_type: str,
        trip_id: str | None = None,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
    ) -> CapturedLodgingLink | None: ...

    def update_decision_status(
        self,
        document_id: str,
        *,
        decision_status: LodgingDecisionStatus,
        source_type: str,
        trip_id: str | None = None,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
        updated_by_user_id: str | None = None,
    ) -> CapturedLodgingLink | None: ...
