from __future__ import annotations

import hashlib
from datetime import date as date_cls
from datetime import datetime, time as time_cls, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

ItineraryItemType = Literal[
    "attraction",
    "food",
    "shopping",
    "transport",
    "lodging",
    "free_time",
    "note",
    "other",
]
ItineraryItemStatus = Literal["confirmed", "tentative", "optional", "cancelled"]
ItineraryDraftStatus = Literal["pending", "applied", "discarded", "failed"]
ItineraryDraftAction = Literal["add", "update", "unchanged", "possible_delete"]


class ItinerarySource(BaseModel):
    source_id: str = Field(default_factory=lambda: uuid4().hex)
    trip_id: str
    trip_title: str | None = None
    source_type: str
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    input_mode: Literal["direct", "quoted"] = "direct"
    source_text: str
    checksum: str = ""
    source_message_id: str | None = None
    quoted_message_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("checksum", mode="before")
    @classmethod
    def _normalize_checksum(cls, value: object) -> str:
        return value if isinstance(value, str) else ""


class ItineraryDayNote(BaseModel):
    note_id: str = Field(default_factory=lambda: uuid4().hex)
    trip_id: str
    source_id: str | None = None
    day_index: int | None = None
    date: date_cls | None = None
    title: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class ItineraryItemPayload(BaseModel):
    day_index: int | None = None
    date: date_cls
    start_time: time_cls | None = None
    end_time: time_cls | None = None
    timezone: str = "Asia/Tokyo"
    title: str
    location_name: str | None = None
    description: str | None = None
    item_type: ItineraryItemType = "other"
    status: ItineraryItemStatus = "confirmed"
    source_line_hash: str | None = None
    fingerprint: str = ""


class ItineraryItem(ItineraryItemPayload):
    item_id: str = Field(default_factory=lambda: uuid4().hex)
    trip_id: str
    trip_title: str | None = None
    source_type: str
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    source_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class ItineraryDraftChange(BaseModel):
    action: ItineraryDraftAction
    item_id: str | None = None
    proposed_item: ItineraryItemPayload | None = None
    existing_item: ItineraryItem | None = None
    reason: str | None = None


class ItineraryDraft(BaseModel):
    draft_id: str = Field(default_factory=lambda: uuid4().hex)
    trip_id: str
    trip_title: str | None = None
    source_type: str
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    source_id: str
    status: ItineraryDraftStatus = "pending"
    changes: list[ItineraryDraftChange] = Field(default_factory=list)
    day_notes: list[ItineraryDayNote] = Field(default_factory=list)
    error: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    applied_at: datetime | None = None
    discarded_at: datetime | None = None


def build_text_checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_source_line_hash(value: str) -> str:
    return hashlib.sha1(" ".join(value.split()).encode("utf-8")).hexdigest()


def build_itinerary_fingerprint(
    *,
    item_date: date_cls,
    start_time: time_cls | None,
    title: str,
    location_name: str | None,
) -> str:
    normalized = "|".join(
        [
            item_date.isoformat(),
            start_time.isoformat(timespec="minutes") if start_time else "",
            _normalize_fingerprint_text(title),
            _normalize_fingerprint_text(location_name or ""),
        ]
    )
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _normalize_fingerprint_text(value: str) -> str:
    return " ".join(value.strip().lower().split())
