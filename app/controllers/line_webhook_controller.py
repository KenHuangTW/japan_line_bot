from __future__ import annotations

import logging

from app.config import Settings
from app.controllers.integration.line_client import LineClient
from app.controllers.repositories.captured_link_repository import (
    CapturedLinkRepository,
)
from app.link_extractor import extract_lodging_links
from app.lodging_links import LodgingLinkService
from app.models import CapturedLodgingLink
from app.schemas.line_webhook import LineWebhookRequest

logger = logging.getLogger(__name__)


async def _safe_reply(
    line_client: LineClient,
    reply_token: str,
    text: str,
) -> None:
    try:
        await line_client.reply_text(reply_token, text)
    except Exception:
        logger.exception("Failed to send LINE reply message.")


async def process_events(
    payload: LineWebhookRequest,
    settings: Settings,
    repository: CapturedLinkRepository,
    line_client: LineClient,
    lodging_link_service: LodgingLinkService,
) -> int:
    captured_total = 0

    for event in payload.events:
        event_type = event.type
        reply_token = event.replyToken

        if (
            event_type == "join"
            and reply_token
            and settings.line_channel_access_token
        ):
            await _safe_reply(
                line_client,
                reply_token,
                settings.line_welcome_message,
            )
            continue

        if event_type != "message" or event.message.type != "text":
            continue

        text = event.message.text
        extracted_matches = extract_lodging_links(text, settings.supported_domains)
        link_matches = await lodging_link_service.filter_supported_lodging_links(
            extracted_matches
        )
        if not link_matches:
            continue

        records = [
            CapturedLodgingLink(
                platform=link.platform,
                url=link.url,
                hostname=link.hostname,
                resolved_url=link.resolved_url,
                resolved_hostname=link.resolved_hostname,
                message_text=text,
                source_type=event.source.type,
                destination=payload.destination,
                group_id=event.source.groupId,
                room_id=event.source.roomId,
                user_id=event.source.userId,
                message_id=event.message.id,
                event_timestamp_ms=event.timestamp,
                event_mode=event.mode,
            )
            for link in link_matches
        ]

        repository.append_many(records)
        captured_count = len(records)
        captured_total += captured_count

        if (
            settings.line_reply_on_capture
            and reply_token
            and settings.line_channel_access_token
        ):
            await _safe_reply(
                line_client,
                reply_token,
                settings.reply_capture_template.format(count=captured_count),
            )

    return captured_total
