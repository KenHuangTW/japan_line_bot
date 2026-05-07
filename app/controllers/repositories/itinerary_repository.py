from __future__ import annotations

from typing import Protocol, Sequence

from app.models import ItineraryDraft, ItineraryItem, ItinerarySource
from app.source_scope import SourceScope


class ItineraryRepository(Protocol):
    def create_source(self, source: ItinerarySource) -> ItinerarySource: ...

    def create_draft(self, draft: ItineraryDraft) -> ItineraryDraft: ...

    def get_latest_pending_draft(
        self,
        source_scope: SourceScope,
    ) -> ItineraryDraft | None: ...

    def mark_draft_applied(self, draft_id: str) -> None: ...

    def mark_draft_discarded(self, draft_id: str) -> None: ...

    def list_items(self, source_scope: SourceScope) -> Sequence[ItineraryItem]: ...

    def upsert_item(self, item: ItineraryItem) -> ItineraryItem: ...

    def mark_item_cancelled(
        self,
        item_id: str,
        source_scope: SourceScope,
    ) -> ItineraryItem | None: ...
