from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field


class LineMessageSnapshot(BaseModel):
    """Stored LINE text message used to resolve later quoted-message commands."""

    message_id: str = Field(description="LINE message id.")
    source_type: str = Field(description="Effective LINE source type.")
    group_id: str | None = Field(default=None)
    room_id: str | None = Field(default=None)
    user_id: str | None = Field(default=None)
    sender_user_id: str | None = Field(default=None)
    message_text: str = Field(description="Inbound text message body.")
    quote_token: str | None = Field(default=None)
    event_timestamp_ms: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = Field(default=None)


def build_line_message_snapshot(
    *,
    message_id: str,
    source_type: str,
    message_text: str,
    group_id: str | None = None,
    room_id: str | None = None,
    user_id: str | None = None,
    sender_user_id: str | None = None,
    quote_token: str | None = None,
    event_timestamp_ms: int | None = None,
    retention_days: int | None = None,
) -> LineMessageSnapshot:
    now = datetime.now(timezone.utc)
    expires_at = (
        now + timedelta(days=retention_days)
        if retention_days is not None and retention_days > 0
        else None
    )
    return LineMessageSnapshot(
        message_id=message_id,
        source_type=source_type,
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        sender_user_id=sender_user_id,
        message_text=message_text,
        quote_token=quote_token,
        event_timestamp_ms=event_timestamp_ms,
        created_at=now,
        expires_at=expires_at,
    )
