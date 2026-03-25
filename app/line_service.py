from __future__ import annotations

from typing import Any

from app.collector import Collector
from app.config import Settings
from app.controllers.line_webhook_controller import (
    process_events as controller_process_events,
)
from app.line_client import LineClient
from app.schemas.line_webhook import LineWebhookRequest


async def process_events(
    payload: dict[str, Any] | LineWebhookRequest,
    settings: Settings,
    collector: Collector,
    line_client: LineClient,
) -> int:
    parsed_payload = (
        payload
        if isinstance(payload, LineWebhookRequest)
        else LineWebhookRequest.model_validate(payload)
    )
    return await controller_process_events(
        payload=parsed_payload,
        settings=settings,
        repository=collector,
        line_client=line_client,
    )

__all__ = ["process_events"]
