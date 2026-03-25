from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LineEventSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = "unknown"
    groupId: str | None = None
    roomId: str | None = None
    userId: str | None = None


class LineMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    type: str | None = None
    text: str = ""


class LineWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str | None = None
    replyToken: str | None = None
    mode: str | None = None
    timestamp: int | None = None
    source: LineEventSource = Field(default_factory=LineEventSource)
    message: LineMessage = Field(default_factory=LineMessage)


class LineWebhookRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    destination: str | None = None
    events: list[LineWebhookEvent] = Field(default_factory=list)


class LineWebhookResponse(BaseModel):
    ok: bool
    captured: int
