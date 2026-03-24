from __future__ import annotations

from typing import Any

from app.collector import Collector
from app.config import Settings
from app.line_client import LineClient
from app.link_extractor import extract_lodging_links
from app.models import CapturedLodgingLink


async def process_events(
    payload: dict[str, Any],
    settings: Settings,
    collector: Collector,
    line_client: LineClient,
) -> int:
    destination = payload.get("destination")
    captured_total = 0

    for event in payload.get("events", []):
        event_type = event.get("type")
        reply_token = event.get("replyToken")

        if (
            event_type == "join"
            and reply_token
            and settings.line_channel_access_token
        ):
            await line_client.reply_text(
                reply_token,
                settings.line_welcome_message,
            )
            continue

        message = event.get("message") or {}
        if event_type != "message" or message.get("type") != "text":
            continue

        text = message.get("text", "")
        link_matches = extract_lodging_links(text, settings.supported_domains)
        if not link_matches:
            continue

        source = event.get("source") or {}
        records = [
            CapturedLodgingLink(
                platform=link.platform,
                url=link.url,
                hostname=link.hostname,
                message_text=text,
                source_type=source.get("type", "unknown"),
                destination=destination,
                group_id=source.get("groupId"),
                room_id=source.get("roomId"),
                user_id=source.get("userId"),
                message_id=message.get("id"),
                event_timestamp_ms=event.get("timestamp"),
                event_mode=event.get("mode"),
            )
            for link in link_matches
        ]

        collector.append_many(records)
        captured_count = len(records)
        captured_total += captured_count

        if (
            settings.line_reply_on_capture
            and reply_token
            and settings.line_channel_access_token
        ):
            await line_client.reply_text(
                reply_token,
                settings.reply_capture_template.format(count=captured_count),
            )

    return captured_total
