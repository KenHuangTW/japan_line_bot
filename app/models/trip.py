from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

TripStatus = Literal["open", "archived"]


class LineTrip(BaseModel):
    """Trip context owned by a LINE chat scope."""

    trip_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="旅次識別碼。",
    )
    title: str = Field(description="旅次名稱。")
    source_type: str = Field(description="LINE source 類型，例如 group 或 room。")
    group_id: str | None = Field(
        default=None,
        description="當 source_type=group 時的 LINE group id。",
    )
    room_id: str | None = Field(
        default=None,
        description="當 source_type=room 時的 LINE room id。",
    )
    user_id: str | None = Field(
        default=None,
        description="當 source_type=user 時的 LINE user id。",
    )
    status: TripStatus = Field(default="open", description="旅次狀態。")
    is_active: bool = Field(default=True, description="是否為目前啟用中的旅次。")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="旅次建立時間。",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="旅次最近更新時間。",
    )
    archived_at: datetime | None = Field(
        default=None,
        description="旅次封存時間。",
    )
