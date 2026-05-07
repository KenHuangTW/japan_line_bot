from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.itinerary.parser import ParsedItinerary, parse_itinerary_markdown
from app.models import (
    ItineraryDayNote,
    ItineraryDraft,
    ItineraryDraftChange,
    ItineraryItem,
    ItineraryItemPayload,
    ItinerarySource,
    LineTrip,
    build_itinerary_fingerprint,
    build_text_checksum,
)
from app.source_scope import SourceScope


class ItineraryImportError(RuntimeError):
    pass


class ItineraryDraftUnavailableError(ItineraryImportError):
    pass


class ItineraryProvider(Protocol):
    async def normalize(
        self,
        parsed: ParsedItinerary,
        *,
        timezone_name: str,
    ) -> "ItineraryNormalizationResult": ...


class ItineraryRepositoryProtocol(Protocol):
    def create_source(self, source: ItinerarySource) -> ItinerarySource: ...

    def create_draft(self, draft: ItineraryDraft) -> ItineraryDraft: ...

    def get_latest_pending_draft(
        self,
        source_scope: SourceScope,
    ) -> ItineraryDraft | None: ...

    def mark_draft_applied(self, draft_id: str) -> None: ...

    def mark_draft_discarded(self, draft_id: str) -> None: ...

    def list_items(self, source_scope: SourceScope): ...

    def upsert_item(self, item: ItineraryItem) -> ItineraryItem: ...

    def mark_item_cancelled(
        self,
        item_id: str,
        source_scope: SourceScope,
    ) -> ItineraryItem | None: ...


@dataclass(frozen=True)
class ItineraryNormalizationResult:
    items: tuple[ItineraryItemPayload, ...]
    day_notes: tuple[ItineraryDayNote, ...]


@dataclass(frozen=True)
class ItineraryDraftResult:
    source: ItinerarySource
    draft: ItineraryDraft


@dataclass(frozen=True)
class ItineraryApplyResult:
    draft: ItineraryDraft
    added: int
    updated: int
    cancelled: int
    unchanged: int


class DeterministicItineraryProvider:
    async def normalize(
        self,
        parsed: ParsedItinerary,
        *,
        timezone_name: str,
    ) -> ItineraryNormalizationResult:
        items = tuple(
            _build_item_payload(row, timezone_name=timezone_name)
            for row in parsed.rows
        )
        day_notes = tuple(
            ItineraryDayNote(
                trip_id="",
                day_index=note.day_index,
                date=note.date,
                title=note.title,
                content=note.content,
            )
            for note in parsed.day_notes
        )
        return ItineraryNormalizationResult(items=items, day_notes=day_notes)


class ItineraryImportService:
    def __init__(
        self,
        repository: ItineraryRepositoryProtocol,
        provider: ItineraryProvider | None = None,
        *,
        timezone_name: str = "Asia/Tokyo",
    ) -> None:
        self.repository = repository
        self.provider = provider or DeterministicItineraryProvider()
        self.timezone_name = timezone_name

    async def create_draft(
        self,
        *,
        trip: LineTrip,
        source_scope: SourceScope,
        source_text: str,
        input_mode: str,
        created_by_user_id: str | None = None,
        source_message_id: str | None = None,
        quoted_message_id: str | None = None,
    ) -> ItineraryDraftResult:
        normalized_text = source_text.strip()
        if not normalized_text:
            raise ItineraryImportError("Itinerary source text is empty.")

        source = ItinerarySource(
            trip_id=trip.trip_id,
            trip_title=trip.title,
            source_type=source_scope.source_type,
            group_id=source_scope.group_id,
            room_id=source_scope.room_id,
            user_id=source_scope.user_id,
            input_mode="quoted" if input_mode == "quoted" else "direct",
            source_text=normalized_text,
            checksum=build_text_checksum(normalized_text),
            source_message_id=source_message_id,
            quoted_message_id=quoted_message_id,
            created_by_user_id=created_by_user_id,
        )
        self.repository.create_source(source)

        parsed = parse_itinerary_markdown(normalized_text)
        if not parsed.rows and not parsed.day_notes:
            raise ItineraryImportError("No itinerary rows or notes were parsed.")

        normalized = await self.provider.normalize(
            parsed,
            timezone_name=self.timezone_name,
        )
        if not normalized.items and not normalized.day_notes:
            raise ItineraryImportError("No itinerary items were normalized.")

        day_notes = tuple(
            note.model_copy(
                update={
                    "trip_id": trip.trip_id,
                    "source_id": source.source_id,
                }
            )
            for note in normalized.day_notes
        )
        proposed_items = tuple(
            _ensure_item_fingerprint(item, timezone_name=self.timezone_name)
            for item in normalized.items
        )
        existing_items = tuple(self.repository.list_items(source_scope))
        draft = ItineraryDraft(
            trip_id=trip.trip_id,
            trip_title=trip.title,
            source_type=source_scope.source_type,
            group_id=source_scope.group_id,
            room_id=source_scope.room_id,
            user_id=source_scope.user_id,
            source_id=source.source_id,
            changes=_build_diff_changes(proposed_items, existing_items),
            day_notes=list(day_notes),
            created_by_user_id=created_by_user_id,
        )
        self.repository.create_draft(draft)
        return ItineraryDraftResult(source=source, draft=draft)

    def discard_latest_draft(self, source_scope: SourceScope) -> ItineraryDraft:
        draft = self.repository.get_latest_pending_draft(source_scope)
        if draft is None:
            raise ItineraryDraftUnavailableError("No pending itinerary draft.")
        self.repository.mark_draft_discarded(draft.draft_id)
        return draft.model_copy(
            update={
                "status": "discarded",
                "discarded_at": datetime.now(timezone.utc),
            }
        )

    def apply_latest_draft(
        self,
        *,
        trip: LineTrip,
        source_scope: SourceScope,
    ) -> ItineraryApplyResult:
        draft = self.repository.get_latest_pending_draft(source_scope)
        if draft is None:
            raise ItineraryDraftUnavailableError("No pending itinerary draft.")

        added = updated = cancelled = unchanged = 0
        for change in draft.changes:
            if change.action == "add" and change.proposed_item is not None:
                self.repository.upsert_item(
                    _build_item_from_payload(
                        change.proposed_item,
                        trip=trip,
                        source_scope=source_scope,
                        source_id=draft.source_id,
                    )
                )
                added += 1
            elif (
                change.action == "update"
                and change.item_id is not None
                and change.proposed_item is not None
            ):
                self.repository.upsert_item(
                    _build_item_from_payload(
                        change.proposed_item,
                        trip=trip,
                        source_scope=source_scope,
                        source_id=draft.source_id,
                        item_id=change.item_id,
                    )
                )
                updated += 1
            elif change.action == "possible_delete" and change.item_id is not None:
                if self.repository.mark_item_cancelled(change.item_id, source_scope):
                    cancelled += 1
            else:
                unchanged += 1

        self.repository.mark_draft_applied(draft.draft_id)
        return ItineraryApplyResult(
            draft=draft.model_copy(
                update={
                    "status": "applied",
                    "applied_at": datetime.now(timezone.utc),
                }
            ),
            added=added,
            updated=updated,
            cancelled=cancelled,
            unchanged=unchanged,
        )

    def list_confirmed_items(self, source_scope: SourceScope) -> tuple[ItineraryItem, ...]:
        return tuple(
            item
            for item in self.repository.list_items(source_scope)
            if item.status != "cancelled"
        )


def _build_item_payload(
    row,
    *,
    timezone_name: str,
) -> ItineraryItemPayload:
    status = _infer_status(row.title, row.description)
    item_type = _infer_item_type(row.title, row.description)
    location_name = _infer_location_name(row.title)
    fingerprint = build_itinerary_fingerprint(
        item_date=row.date,
        start_time=row.start_time,
        title=row.title,
        location_name=location_name,
    )
    return ItineraryItemPayload(
        day_index=row.day_index,
        date=row.date,
        start_time=row.start_time,
        end_time=row.end_time,
        timezone=timezone_name,
        title=row.title,
        location_name=location_name,
        description=row.description,
        item_type=item_type,
        status=status,
        source_line_hash=row.source_line_hash,
        fingerprint=fingerprint,
    )


def _build_diff_changes(
    proposed_items: tuple[ItineraryItemPayload, ...],
    existing_items: tuple[ItineraryItem, ...],
) -> list[ItineraryDraftChange]:
    existing_by_fingerprint = {
        item.fingerprint: item for item in existing_items if item.status != "cancelled"
    }
    existing_by_identity = {
        _identity_key(item): item for item in existing_items if item.status != "cancelled"
    }
    matched_item_ids: set[str] = set()
    changes: list[ItineraryDraftChange] = []

    for proposed in proposed_items:
        existing = existing_by_fingerprint.get(proposed.fingerprint)
        if existing is not None:
            matched_item_ids.add(existing.item_id)
            changes.append(
                ItineraryDraftChange(
                    action="unchanged",
                    item_id=existing.item_id,
                    proposed_item=proposed,
                    existing_item=existing,
                )
            )
            continue

        existing = existing_by_identity.get(_identity_key(proposed))
        if existing is not None:
            matched_item_ids.add(existing.item_id)
            changes.append(
                ItineraryDraftChange(
                    action="update",
                    item_id=existing.item_id,
                    proposed_item=proposed,
                    existing_item=existing,
                )
            )
            continue

        changes.append(ItineraryDraftChange(action="add", proposed_item=proposed))

    for existing in existing_items:
        if existing.status == "cancelled" or existing.item_id in matched_item_ids:
            continue
        changes.append(
            ItineraryDraftChange(
                action="possible_delete",
                item_id=existing.item_id,
                existing_item=existing,
            )
        )

    return changes


def _build_item_from_payload(
    payload: ItineraryItemPayload,
    *,
    trip: LineTrip,
    source_scope: SourceScope,
    source_id: str,
    item_id: str | None = None,
) -> ItineraryItem:
    data = {
        "trip_id": trip.trip_id,
        "trip_title": trip.title,
        "source_type": source_scope.source_type,
        "group_id": source_scope.group_id,
        "room_id": source_scope.room_id,
        "user_id": source_scope.user_id,
        "source_id": source_id,
        **payload.model_dump(mode="python"),
    }
    if item_id is not None:
        data["item_id"] = item_id
    return ItineraryItem(**data)


def _ensure_item_fingerprint(
    item: ItineraryItemPayload,
    *,
    timezone_name: str,
) -> ItineraryItemPayload:
    fingerprint = item.fingerprint or build_itinerary_fingerprint(
        item_date=item.date,
        start_time=item.start_time,
        title=item.title,
        location_name=item.location_name,
    )
    return item.model_copy(
        update={
            "timezone": item.timezone or timezone_name,
            "fingerprint": fingerprint,
        }
    )


def _identity_key(item) -> tuple[str, str, str]:
    return (
        item.date.isoformat(),
        _normalize_identity_text(item.title),
        _normalize_identity_text(item.location_name or ""),
    )


def _normalize_identity_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _infer_status(title: str, description: str | None) -> str:
    text = f"{title} {description or ''}"
    if "可選" in text:
        return "optional"
    if "自由" in text or "待確認" in text:
        return "tentative"
    return "confirmed"


def _infer_item_type(title: str, description: str | None) -> str:
    text = f"{title} {description or ''}".lower()
    if any(keyword in text for keyword in ("站 →", "→", "巴士", "特急", "機場")):
        return "transport"
    if any(keyword in text for keyword in ("午餐", "晚餐", "餐", "拉麵", "燒肉", "居酒屋")):
        return "food"
    if any(keyword in text for keyword in ("百貨", "parco", "唐吉", "購物", "商店", "地下街")):
        return "shopping"
    if any(keyword in text for keyword in ("飯店", "check-in", "住宿")):
        return "lodging"
    if "自由" in text:
        return "free_time"
    if any(keyword in text for keyword in ("神社", "觀音", "城", "庭園", "碼頭", "公園")):
        return "attraction"
    return "other"


def _infer_location_name(title: str) -> str | None:
    normalized = title.strip()
    if not normalized:
        return None
    if "→" in normalized:
        return None
    if "自由" in normalized:
        return None
    return normalized
