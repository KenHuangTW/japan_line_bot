from __future__ import annotations

import asyncio
from datetime import date, time
from typing import Sequence

import httpx
import pytest

from app.itinerary import (
    GeminiItineraryProvider,
    ItineraryImportError,
    ItineraryImportService,
)
from app.itinerary.parser import parse_itinerary_markdown
from app.models import ItineraryDraft, ItineraryItem, ItinerarySource, LineTrip
from app.source_scope import SourceScope

SAMPLE_ITINERARY = """\
## 第 1 天 — 2026-06-01（市區）

- 09:30–11:00 | 若宮八幡社 | 抵達名古屋後輕鬆參拜
- 12:30–13:30 | 矢場とん 矢場町本店（可選） | 午餐選項
- 18:00–（自由） | 晚餐自由 | 榮周邊自由找餐廳

今日購物重點
- Parco 名古屋
"""


class InMemoryItineraryRepository:
    def __init__(self) -> None:
        self.sources: list[ItinerarySource] = []
        self.drafts: list[ItineraryDraft] = []
        self.items: list[ItineraryItem] = []

    def create_source(self, source: ItinerarySource) -> ItinerarySource:
        self.sources.append(source)
        return source

    def create_draft(self, draft: ItineraryDraft) -> ItineraryDraft:
        self.drafts.append(draft)
        return draft

    def get_latest_pending_draft(self, source_scope: SourceScope):
        for draft in reversed(self.drafts):
            if draft.status == "pending" and _matches_scope(draft, source_scope):
                return draft
        return None

    def mark_draft_applied(self, draft_id: str) -> None:
        for index, draft in enumerate(self.drafts):
            if draft.draft_id == draft_id:
                self.drafts[index] = draft.model_copy(update={"status": "applied"})

    def mark_draft_discarded(self, draft_id: str) -> None:
        for index, draft in enumerate(self.drafts):
            if draft.draft_id == draft_id:
                self.drafts[index] = draft.model_copy(update={"status": "discarded"})

    def list_items(self, source_scope: SourceScope) -> Sequence[ItineraryItem]:
        return [
            item for item in self.items if _matches_scope(item, source_scope)
        ]

    def upsert_item(self, item: ItineraryItem) -> ItineraryItem:
        for index, current in enumerate(self.items):
            if current.item_id == item.item_id:
                self.items[index] = item
                return item
        self.items.append(item)
        return item

    def mark_item_cancelled(self, item_id: str, source_scope: SourceScope):
        for index, item in enumerate(self.items):
            if item.item_id == item_id and _matches_scope(item, source_scope):
                updated = item.model_copy(update={"status": "cancelled"})
                self.items[index] = updated
                return updated
        return None


def test_parse_itinerary_markdown_extracts_rows_and_notes() -> None:
    parsed = parse_itinerary_markdown(SAMPLE_ITINERARY)

    assert len(parsed.rows) == 3
    assert parsed.rows[0].date == date(2026, 6, 1)
    assert parsed.rows[0].start_time == time(9, 30)
    assert parsed.rows[0].end_time == time(11, 0)
    assert parsed.rows[1].title == "矢場とん 矢場町本店（可選）"
    assert parsed.rows[2].end_time is None
    assert len(parsed.day_notes) == 1
    assert parsed.day_notes[0].title == "今日購物重點"


def test_itinerary_import_service_creates_draft_and_applies_items() -> None:
    repository = InMemoryItineraryRepository()
    service = ItineraryImportService(repository)
    trip = _build_trip()
    scope = _build_scope()

    result = asyncio.run(
        service.create_draft(
            trip=trip,
            source_scope=scope,
            source_text=SAMPLE_ITINERARY,
            input_mode="direct",
            created_by_user_id="Uuser",
        )
    )
    apply_result = service.apply_latest_draft(trip=trip, source_scope=scope)

    assert repository.sources[0].source_text == SAMPLE_ITINERARY.strip()
    assert len(result.draft.changes) == 3
    assert {change.action for change in result.draft.changes} == {"add"}
    assert result.draft.day_notes[0].content == "Parco 名古屋"
    assert apply_result.added == 3
    assert len(service.list_confirmed_items(scope)) == 3
    statuses = {item.title: item.status for item in repository.items}
    assert statuses["矢場とん 矢場町本店（可選）"] == "optional"
    assert statuses["晚餐自由"] == "tentative"


def test_itinerary_import_service_builds_update_and_possible_delete_diff() -> None:
    repository = InMemoryItineraryRepository()
    service = ItineraryImportService(repository)
    trip = _build_trip()
    scope = _build_scope()

    asyncio.run(
        service.create_draft(
            trip=trip,
            source_scope=scope,
            source_text=SAMPLE_ITINERARY,
            input_mode="direct",
        )
    )
    service.apply_latest_draft(trip=trip, source_scope=scope)

    revised = """\
## 第 1 天 — 2026-06-01（市區）

- 10:00–11:30 | 若宮八幡社 | 改成晚一點抵達
- 14:00–15:00 | 三輪神社 | 小巧可愛的在地神社
"""
    result = asyncio.run(
        service.create_draft(
            trip=trip,
            source_scope=scope,
            source_text=revised,
            input_mode="direct",
        )
    )

    actions = [change.action for change in result.draft.changes]
    assert actions.count("update") == 1
    assert actions.count("add") == 1
    assert actions.count("possible_delete") == 2


def test_itinerary_import_service_rejects_unparseable_text() -> None:
    service = ItineraryImportService(InMemoryItineraryRepository())
    with pytest.raises(ItineraryImportError):
        asyncio.run(
            service.create_draft(
                trip=_build_trip(),
                source_scope=_build_scope(),
                source_text="只是閒聊",
                input_mode="direct",
            )
        )


def test_gemini_itinerary_provider_falls_back_to_deterministic_parser() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="temporarily unavailable")

    provider = GeminiItineraryProvider(
        "fake-key",
        transport=httpx.MockTransport(handler),
        retry_backoff_seconds=0,
    )
    parsed = parse_itinerary_markdown(SAMPLE_ITINERARY)

    result = asyncio.run(provider.normalize(parsed, timezone_name="Asia/Tokyo"))

    assert len(result.items) == 3
    assert result.items[0].title == "若宮八幡社"
    assert result.items[1].status == "optional"
    assert result.items[2].status == "tentative"


def _build_trip() -> LineTrip:
    return LineTrip(
        trip_id="trip-current",
        title="名古屋 2026",
        source_type="group",
        group_id="Cgroup123",
        user_id="Uuser123",
    )


def _build_scope() -> SourceScope:
    return SourceScope(
        source_type="group",
        group_id="Cgroup123",
        user_id="Uuser123",
        trip_id="trip-current",
        trip_title="名古屋 2026",
    )


def _matches_scope(item, scope: SourceScope) -> bool:
    return (
        item.source_type == scope.source_type
        and item.trip_id == scope.trip_id
        and item.group_id == scope.group_id
    )
