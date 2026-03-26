from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

MapStatus = Literal["pending", "resolved", "failed"]


class LodgingLinkMatch(BaseModel):
    """Normalized lodging link extracted from a chat message."""

    platform: str = Field(description="住宿平台識別，例如 booking 或 agoda。")
    url: str = Field(description="從訊息中擷取出的原始住宿連結。")
    hostname: str = Field(description="住宿連結對應的 hostname。")
    resolved_url: str | None = Field(
        default=None,
        description="解析後可確認為住宿頁的最終連結。",
    )
    resolved_hostname: str | None = Field(
        default=None,
        description="解析後最終住宿連結對應的 hostname。",
    )


class CapturedLodgingLink(BaseModel):
    """MongoDB document payload for a captured lodging link event."""

    platform: str = Field(description="住宿平台識別，例如 booking 或 agoda。")
    url: str = Field(description="從 LINE 訊息中擷取出的原始住宿連結。")
    hostname: str = Field(description="住宿連結對應的 hostname。")
    resolved_url: str | None = Field(
        default=None,
        description="解析後可確認為住宿頁的最終連結。",
    )
    resolved_hostname: str | None = Field(
        default=None,
        description="解析後最終住宿連結對應的 hostname。",
    )
    property_name: str | None = Field(
        default=None,
        description="解析住宿頁後得到的住宿名稱。",
    )
    formatted_address: str | None = Field(
        default=None,
        description="解析住宿頁後得到的格式化地址。",
    )
    latitude: float | None = Field(
        default=None,
        description="住宿地點緯度。",
    )
    longitude: float | None = Field(
        default=None,
        description="住宿地點經度。",
    )
    place_id: str | None = Field(
        default=None,
        description="Google Maps / Places 對應的 place_id，若尚未解析則為空。",
    )
    google_maps_url: str | None = Field(
        default=None,
        description="以經緯度開啟 Google Maps 的定位連結；若尚未取得座標則為空。",
    )
    map_source: str | None = Field(
        default=None,
        description="地圖資訊來源，例如 structured_data_geo 或 structured_data_address。",
    )
    map_status: MapStatus = Field(
        default="pending",
        description="地圖資訊解析狀態。",
    )
    map_error: str | None = Field(
        default=None,
        description="地圖資訊解析失敗時的錯誤摘要。",
    )
    map_retry_count: int = Field(
        default=0,
        description="地圖資訊解析已重試次數。",
    )
    map_last_attempt_at: datetime | None = Field(
        default=None,
        description="最後一次嘗試解析地圖資訊的 UTC 時間。",
    )
    map_resolved_at: datetime | None = Field(
        default=None,
        description="成功解析地圖資訊的 UTC 時間。",
    )
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
