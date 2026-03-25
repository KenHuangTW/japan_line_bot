from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class LodgingLinkMatch(BaseModel):
    platform: str
    url: str
    hostname: str


class CapturedLodgingLink(BaseModel):
    platform: str
    url: str
    hostname: str
    message_text: str
    source_type: str
    destination: str | None = None
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    message_id: str | None = None
    event_timestamp_ms: int | None = None
    event_mode: str | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
