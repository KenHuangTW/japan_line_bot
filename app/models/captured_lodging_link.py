from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class LodgingLinkMatch(BaseModel):
    """Normalized lodging link extracted from a chat message."""

    platform: str = Field(description="住宿平台識別，例如 booking 或 agoda。")
    url: str = Field(description="從訊息中擷取出的原始住宿連結。")
    hostname: str = Field(description="住宿連結對應的 hostname。")


class CapturedLodgingLink(BaseModel):
    """MongoDB document payload for a captured lodging link event."""

    platform: str = Field(description="住宿平台識別，例如 booking 或 agoda。")
    url: str = Field(description="從 LINE 訊息中擷取出的原始住宿連結。")
    hostname: str = Field(description="住宿連結對應的 hostname。")
    message_text: str = Field(description="使用者送出的原始文字訊息。")
    source_type: str = Field(description="LINE webhook source 類型，例如 group 或 room。")
    destination: str | None = Field(
        default=None,
        description="LINE bot destination identifier。",
    )
    group_id: str | None = Field(
        default=None,
        description="群組訊息來源時的 LINE groupId。",
    )
    room_id: str | None = Field(
        default=None,
        description="聊天室訊息來源時的 LINE roomId。",
    )
    user_id: str | None = Field(
        default=None,
        description="觸發事件的 LINE userId。",
    )
    message_id: str | None = Field(
        default=None,
        description="LINE message id。",
    )
    event_timestamp_ms: int | None = Field(
        default=None,
        description="LINE webhook event timestamp，單位為毫秒。",
    )
    event_mode: str | None = Field(
        default=None,
        description="LINE webhook mode，例如 active。",
    )
    # Persist UTC timestamps so MongoDB documents stay comparable across environments.
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="系統完成擷取時的 UTC 時間。",
    )
