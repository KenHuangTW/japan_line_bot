from __future__ import annotations

from typing import Protocol, Sequence

from app.models import CapturedLodgingLink


class CapturedLinkRepository(Protocol):
    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int: ...
