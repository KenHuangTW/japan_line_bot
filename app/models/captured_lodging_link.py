from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

MapStatus = Literal["pending", "resolved", "partial", "failed"]
SyncStatus = Literal["pending", "synced", "failed"]


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
    street_address: str | None = Field(
        default=None,
        description="結構化後的街道地址。",
    )
    district: str | None = Field(
        default=None,
        description="結構化後的區域資訊，例如 ward 或 district。",
    )
    city: str | None = Field(
        default=None,
        description="結構化後的城市名稱。",
    )
    region: str | None = Field(
        default=None,
        description="結構化後的州 / 省 / 都道府縣資訊。",
    )
    postal_code: str | None = Field(
        default=None,
        description="結構化後的郵遞區號。",
    )
    country_name: str | None = Field(
        default=None,
        description="結構化後的國家名稱。",
    )
    country_code: str | None = Field(
        default=None,
        description="結構化後的國家代碼，例如 JP。",
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
        description="以經緯度開啟 Google Maps 的精準定位連結；若尚未取得座標則為空。",
    )
    google_maps_search_url: str | None = Field(
        default=None,
        description="以住宿名稱或地址搜尋 Google Maps 的備援連結。",
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
    property_type: str | None = Field(
        default=None,
        description="住宿類型，例如 hotel 或 vacationrental。",
    )
    room_count: int | None = Field(
        default=None,
        description="住宿頁標示的總房間數。",
    )
    bedroom_count: int | None = Field(
        default=None,
        description="住宿頁標示的臥室數量。",
    )
    bathroom_count: float | None = Field(
        default=None,
        description="住宿頁標示的衛浴數量。",
    )
    amenities: list[str] = Field(
        default_factory=list,
        description="住宿頁標示的設備清單。",
    )
    details_source: str | None = Field(
        default=None,
        description="住宿細節資訊來源。",
    )
    details_status: MapStatus = Field(
        default="pending",
        description="住宿細節解析狀態。",
    )
    details_error: str | None = Field(
        default=None,
        description="住宿細節解析失敗時的錯誤摘要。",
    )
    details_retry_count: int = Field(
        default=0,
        description="住宿細節解析已重試次數。",
    )
    details_last_attempt_at: datetime | None = Field(
        default=None,
        description="最後一次嘗試解析住宿細節的 UTC 時間。",
    )
    details_resolved_at: datetime | None = Field(
        default=None,
        description="成功解析住宿細節的 UTC 時間。",
    )
    price_amount: float | None = Field(
        default=None,
        description="轉換後用於顯示的價格數值。",
    )
    price_currency: str | None = Field(
        default=None,
        description="轉換後用於顯示的價格幣別。",
    )
    source_price_amount: float | None = Field(
        default=None,
        description="住宿頁原始揭露的價格數值。",
    )
    source_price_currency: str | None = Field(
        default=None,
        description="住宿頁原始揭露的價格幣別。",
    )
    price_exchange_rate: float | None = Field(
        default=None,
        description="將原始幣別轉為顯示幣別時使用的匯率。",
    )
    price_exchange_rate_source: str | None = Field(
        default=None,
        description="顯示幣別匯率來源。",
    )
    is_sold_out: bool | None = Field(
        default=None,
        description="住宿是否已售完。null 代表目前無法判定。",
    )
    availability_source: str | None = Field(
        default=None,
        description="售完狀態判斷來源。",
    )
    pricing_source: str | None = Field(
        default=None,
        description="價格資訊來源。",
    )
    pricing_status: MapStatus = Field(
        default="pending",
        description="價格資訊解析狀態。",
    )
    pricing_error: str | None = Field(
        default=None,
        description="價格資訊解析失敗時的錯誤摘要。",
    )
    pricing_retry_count: int = Field(
        default=0,
        description="價格資訊解析已重試次數。",
    )
    pricing_last_attempt_at: datetime | None = Field(
        default=None,
        description="最後一次嘗試解析價格資訊的 UTC 時間。",
    )
    pricing_resolved_at: datetime | None = Field(
        default=None,
        description="成功解析價格資訊的 UTC 時間。",
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
    notion_page_id: str | None = Field(
        default=None,
        description="同步到 Notion 後對應的 page id。",
    )
    notion_page_url: str | None = Field(
        default=None,
        description="同步到 Notion 後對應的 page URL。",
    )
    notion_database_id: str | None = Field(
        default=None,
        description="同步到 Notion 後對應的 database id。",
    )
    notion_data_source_id: str | None = Field(
        default=None,
        description="同步到 Notion 後對應的 data source id。",
    )
    notion_sync_status: SyncStatus = Field(
        default="pending",
        description="同步到 Notion 的狀態。",
    )
    notion_sync_error: str | None = Field(
        default=None,
        description="同步到 Notion 失敗時的錯誤摘要。",
    )
    notion_sync_retry_count: int = Field(
        default=0,
        description="同步到 Notion 已重試次數。",
    )
    notion_last_attempt_at: datetime | None = Field(
        default=None,
        description="最後一次嘗試同步到 Notion 的 UTC 時間。",
    )
    notion_last_synced_at: datetime | None = Field(
        default=None,
        description="最後一次成功同步到 Notion 的 UTC 時間。",
    )
    # Persist UTC timestamps so MongoDB documents stay comparable across environments.
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="系統完成擷取時的 UTC 時間。",
    )
