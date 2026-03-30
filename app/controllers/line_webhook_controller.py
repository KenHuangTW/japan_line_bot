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
from app.notion_sync import (
    NotionLodgingSyncService,
    NotionSyncRepository,
    NotionSyncSummary,
    NotionSyncSourceScope,
    run_notion_sync_job,
)
from app.schemas.line_webhook import LineEventSource, LineWebhookRequest

logger = logging.getLogger(__name__)

PING_COMMAND = "/ping"
NOTION_SYNC_PENDING_COMMAND = "/整理"
NOTION_SYNC_FORCE_COMMAND = "/全部重來"


async def _safe_reply(
    line_client: LineClient,
    reply_token: str,
    text: str,
) -> None:
    try:
        await line_client.reply_text(reply_token, text)
    except Exception:
        logger.exception("Failed to send LINE reply message.")


async def _handle_line_command(
    *,
    text: str,
    source: LineEventSource,
    reply_token: str | None,
    settings: Settings,
    line_client: LineClient,
    notion_sync_repository: NotionSyncRepository | None,
    notion_sync_service: NotionLodgingSyncService | None,
) -> bool:
    command = text.strip()
    if command == PING_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text="pong",
        )
        return True

    if command == NOTION_SYNC_PENDING_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=await _run_notion_sync_command(
                repository=notion_sync_repository,
                service=notion_sync_service,
                force=False,
                source_scope=_build_source_scope(source),
            ),
        )
        return True

    if command == NOTION_SYNC_FORCE_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=await _run_notion_sync_command(
                repository=notion_sync_repository,
                service=notion_sync_service,
                force=True,
                source_scope=_build_source_scope(source),
            ),
        )
        return True

    return False


async def _reply_if_possible(
    *,
    settings: Settings,
    line_client: LineClient,
    reply_token: str | None,
    text: str,
) -> None:
    if reply_token and settings.line_channel_access_token:
        await _safe_reply(line_client, reply_token, text)


async def _run_notion_sync_command(
    *,
    repository: NotionSyncRepository | None,
    service: NotionLodgingSyncService | None,
    force: bool,
    source_scope: NotionSyncSourceScope | None,
) -> str:
    if source_scope is None:
        return "無法辨識目前聊天室，暫時無法執行 Notion sync。"

    if repository is None or service is None or not service.is_sync_configured:
        return "Notion sync 尚未設定完成。"

    try:
        if force:
            await service.setup_database()
        summary = await run_notion_sync_job(
            repository=repository,
            service=service,
            limit=None,
            force=force,
            source_scope=source_scope,
        )
    except Exception:
        logger.exception("Failed to run Notion sync command from LINE.")
        action = "全部重來" if force else "整理"
        return f"Notion {action}失敗，請稍後再試。"

    return _format_notion_sync_summary(summary=summary, force=force)


def _format_notion_sync_summary(
    *,
    summary: NotionSyncSummary,
    force: bool,
) -> str:
    action = "全部重來" if force else "整理"
    return (
        f"Notion {action}完成："
        f"處理 {summary.processed} 筆，"
        f"新增 {summary.created} 筆，"
        f"更新 {summary.updated} 筆，"
        f"失敗 {summary.failed} 筆。"
    )


def _build_source_scope(source: LineEventSource) -> NotionSyncSourceScope | None:
    source_type = (source.type or "").strip().lower()
    if source_type == "group" and source.groupId:
        return NotionSyncSourceScope(
            source_type="group",
            group_id=source.groupId,
        )
    if source_type == "room" and source.roomId:
        return NotionSyncSourceScope(
            source_type="room",
            room_id=source.roomId,
        )
    if source_type == "user" and source.userId:
        return NotionSyncSourceScope(
            source_type="user",
            user_id=source.userId,
        )
    return None


async def process_events(
    payload: LineWebhookRequest,
    settings: Settings,
    repository: CapturedLinkRepository,
    line_client: LineClient,
    lodging_link_service: LodgingLinkService,
    notion_sync_repository: NotionSyncRepository | None = None,
    notion_sync_service: NotionLodgingSyncService | None = None,
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
        if await _handle_line_command(
            text=text,
            source=event.source,
            reply_token=reply_token,
            settings=settings,
            line_client=line_client,
            notion_sync_repository=notion_sync_repository,
            notion_sync_service=notion_sync_service,
        ):
            continue

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
