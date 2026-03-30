from __future__ import annotations

from typing import Protocol, Sequence

from app.models import CapturedLodgingLink


class CapturedLinkRepository(Protocol):
    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int: ...

    def find_duplicate(
        self,
        urls: Sequence[str],
        *,
        source_type: str,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
    ) -> CapturedLodgingLink | None: ...
