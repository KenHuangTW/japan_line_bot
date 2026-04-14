from __future__ import annotations

import logging

from app.config import Settings
from app.controllers.integration.line_client import LineClient
from app.controllers.repositories.captured_link_repository import CapturedLinkRepository
from app.controllers.repositories.trip_repository import TripRepository
from app.link_extractor import extract_lodging_links
from app.lodging_links import LodgingLinkService
from app.lodging_links.common import build_lodging_lookup_keys
from app.map_enrichment import (
    LodgingMapEnrichmentService,
    MapEnrichmentRepository,
    retry_all_map_enrichment_documents,
    run_map_enrichment_job,
)
from app.models import CapturedLodgingLink, LineTrip, LodgingLinkMatch
from app.notion_sync import (
    NotionSyncRepository,
    NotionSyncSourceScope,
    NotionSyncSummary,
    NotionTargetManager,
    build_source_scope,
    run_notion_sync_job,
)
from app.schemas.line_webhook import LineEventSource, LineWebhookRequest

logger = logging.getLogger(__name__)

HELP_COMMAND = "/help"
PING_COMMAND = "/ping"
TRIP_CREATE_COMMAND = "/建立旅次"
TRIP_SWITCH_COMMAND = "/切換旅次"
TRIP_CURRENT_COMMAND = "/目前旅次"
TRIP_ARCHIVE_COMMAND = "/封存旅次"
NOTION_LIST_COMMAND = "/清單"
NOTION_SYNC_PENDING_COMMAND = "/整理"
NOTION_SYNC_FORCE_COMMAND = "/全部重來"
TRIP_FEATURE_UNAVAILABLE_MESSAGE = "旅次功能尚未設定完成。"
TRIP_REQUIRED_MESSAGE = (
    "目前沒有啟用中的旅次，請先用 /建立旅次 <名稱> 建立，或用 /切換旅次 <名稱> 切換。"
)
TRIP_CAPTURE_REQUIRED_MESSAGE = (
    "請先建立或切換旅次，再貼住宿連結。用法：/建立旅次 <名稱> 或 /切換旅次 <名稱>"
)
LINE_COMMAND_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    (HELP_COMMAND, "顯示目前支援的指令與說明"),
    (PING_COMMAND, "回覆 pong"),
    (TRIP_CREATE_COMMAND, "建立新旅次並切換為目前旅次，格式：/建立旅次 <名稱>"),
    (TRIP_SWITCH_COMMAND, "切換到既有旅次，格式：/切換旅次 <名稱>"),
    (TRIP_CURRENT_COMMAND, "查看目前啟用中的旅次"),
    (TRIP_ARCHIVE_COMMAND, "封存目前旅次並清空 active trip"),
    (NOTION_LIST_COMMAND, "直接回傳目前旅次的 Notion 住宿清單連結"),
    (
        NOTION_SYNC_PENDING_COMMAND,
        "執行 Notion sync，只整理目前旅次中 pending / 尚未同步完成的資料",
    ),
    (
        NOTION_SYNC_FORCE_COMMAND,
        "忽略既有同步狀態，只把目前旅次中的資料強制重新同步到 Notion",
    ),
)


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
    trip_repository: TripRepository | None,
    notion_sync_repository: NotionSyncRepository | None,
    notion_target_manager: NotionTargetManager,
    map_enrichment_repository: MapEnrichmentRepository | None,
    map_enrichment_service: LodgingMapEnrichmentService | None,
) -> bool:
    command, argument = _split_command_text(text)
    if command == HELP_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=_format_help_message(),
        )
        return True

    if command == PING_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text="pong",
        )
        return True

    if command == TRIP_CREATE_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=_run_trip_create_command(
                source=source,
                title=argument,
                trip_repository=trip_repository,
            ),
        )
        return True

    if command == TRIP_SWITCH_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=_run_trip_switch_command(
                source=source,
                title=argument,
                trip_repository=trip_repository,
            ),
        )
        return True

    if command == TRIP_CURRENT_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=_run_trip_current_command(
                source=source,
                trip_repository=trip_repository,
            ),
        )
        return True

    if command == TRIP_ARCHIVE_COMMAND:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=_run_trip_archive_command(
                source=source,
                trip_repository=trip_repository,
            ),
        )
        return True

    if command == NOTION_LIST_COMMAND:
        trip_scope, _, error_message = _resolve_active_trip_scope(
            source=source,
            trip_repository=trip_repository,
            action_label="查詢目前旅次",
        )
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=(
                error_message
                if error_message is not None
                else await _run_notion_list_command(
                    settings=settings,
                    target_manager=notion_target_manager,
                    source_scope=trip_scope,
                )
            ),
        )
        return True

    if command == NOTION_SYNC_PENDING_COMMAND:
        trip_scope, _, error_message = _resolve_active_trip_scope(
            source=source,
            trip_repository=trip_repository,
            action_label="執行 Notion sync",
        )
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=(
                error_message
                if error_message is not None
                else await _run_notion_sync_command(
                    repository=notion_sync_repository,
                    target_manager=notion_target_manager,
                    force=False,
                    source_scope=trip_scope,
                    map_enrichment_repository=map_enrichment_repository,
                    map_enrichment_service=map_enrichment_service,
                )
            ),
        )
        return True

    if command == NOTION_SYNC_FORCE_COMMAND:
        trip_scope, _, error_message = _resolve_active_trip_scope(
            source=source,
            trip_repository=trip_repository,
            action_label="執行 Notion sync",
        )
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=(
                error_message
                if error_message is not None
                else await _run_notion_sync_command(
                    repository=notion_sync_repository,
                    target_manager=notion_target_manager,
                    force=True,
                    source_scope=trip_scope,
                    map_enrichment_repository=map_enrichment_repository,
                    map_enrichment_service=map_enrichment_service,
                )
            ),
        )
        return True

    return False


def _split_command_text(text: str) -> tuple[str, str | None]:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return "", None
    if len(parts) == 1:
        return parts[0], None
    argument = parts[1].strip()
    return parts[0], argument or None


async def _reply_if_possible(
    *,
    settings: Settings,
    line_client: LineClient,
    reply_token: str | None,
    text: str,
) -> None:
    if reply_token and settings.line_channel_access_token:
        await _safe_reply(line_client, reply_token, text)


def _build_duplicate_lookup_urls(match: LodgingLinkMatch) -> list[str]:
    lookup_urls: list[str] = []
    for candidate_url in (match.url, match.resolved_url):
        if candidate_url and candidate_url not in lookup_urls:
            lookup_urls.append(candidate_url)
    for candidate_url in build_lodging_lookup_keys(match.url, match.resolved_url):
        if candidate_url not in lookup_urls:
            lookup_urls.append(candidate_url)
    return lookup_urls


def _uses_short_link(
    *,
    url: str,
    resolved_url: str | None,
) -> bool:
    return bool(resolved_url and resolved_url != url)


def _select_duplicate_reply_url(
    *,
    match: LodgingLinkMatch,
    duplicate: CapturedLodgingLink,
) -> str:
    if _uses_short_link(url=duplicate.url, resolved_url=duplicate.resolved_url):
        return duplicate.url
    if _uses_short_link(url=match.url, resolved_url=match.resolved_url):
        return match.url
    return duplicate.resolved_url or duplicate.url


def _run_trip_create_command(
    *,
    source: LineEventSource,
    title: str | None,
    trip_repository: TripRepository | None,
) -> str:
    chat_scope, error_message = _resolve_chat_scope(
        source=source,
        action_label="建立旅次",
    )
    if error_message is not None:
        return error_message
    if trip_repository is None:
        return TRIP_FEATURE_UNAVAILABLE_MESSAGE
    if not title:
        return f"請提供旅次名稱，格式：{TRIP_CREATE_COMMAND} <名稱>"

    try:
        existing_trip = trip_repository.find_open_trip_by_title(chat_scope, title)
    except ValueError:
        return f"請提供旅次名稱，格式：{TRIP_CREATE_COMMAND} <名稱>"

    if existing_trip is not None:
        if existing_trip.is_active:
            return f"目前旅次已經是：{existing_trip.title}"
        switched_trip = trip_repository.switch_active_trip(chat_scope, existing_trip.title)
        if switched_trip is None:
            return f"找不到旅次：{existing_trip.title}"
        return f"旅次已存在，已切換到：{switched_trip.title}"

    trip = trip_repository.create_trip(chat_scope, title)
    return f"已建立並切換到旅次：{trip.title}"


def _run_trip_switch_command(
    *,
    source: LineEventSource,
    title: str | None,
    trip_repository: TripRepository | None,
) -> str:
    chat_scope, error_message = _resolve_chat_scope(
        source=source,
        action_label="切換旅次",
    )
    if error_message is not None:
        return error_message
    if trip_repository is None:
        return TRIP_FEATURE_UNAVAILABLE_MESSAGE
    if not title:
        return f"請提供旅次名稱，格式：{TRIP_SWITCH_COMMAND} <名稱>"

    try:
        trip = trip_repository.switch_active_trip(chat_scope, title)
    except ValueError:
        return f"請提供旅次名稱，格式：{TRIP_SWITCH_COMMAND} <名稱>"

    if trip is None:
        return f"找不到旅次：{title.strip()}"
    return f"目前旅次已切換為：{trip.title}"


def _run_trip_current_command(
    *,
    source: LineEventSource,
    trip_repository: TripRepository | None,
) -> str:
    _, trip, error_message = _resolve_active_trip_scope(
        source=source,
        trip_repository=trip_repository,
        action_label="查詢目前旅次",
    )
    if error_message is not None:
        return error_message
    assert trip is not None
    return (
        f"目前旅次：{trip.title}\n"
        f"旅次 ID：{trip.trip_id}\n"
        "狀態：進行中"
    )


def _run_trip_archive_command(
    *,
    source: LineEventSource,
    trip_repository: TripRepository | None,
) -> str:
    chat_scope, error_message = _resolve_chat_scope(
        source=source,
        action_label="封存旅次",
    )
    if error_message is not None:
        return error_message
    if trip_repository is None:
        return TRIP_FEATURE_UNAVAILABLE_MESSAGE
    archived_trip = trip_repository.archive_active_trip(chat_scope)
    if archived_trip is None:
        return TRIP_REQUIRED_MESSAGE
    return f"已封存旅次：{archived_trip.title}"


def _resolve_chat_scope(
    *,
    source: LineEventSource,
    action_label: str,
) -> tuple[NotionSyncSourceScope | None, str | None]:
    source_scope = _build_source_scope(source)
    if source_scope is None:
        return None, f"無法辨識目前聊天室，暫時無法{action_label}。"
    return source_scope, None


def _resolve_active_trip_scope(
    *,
    source: LineEventSource,
    trip_repository: TripRepository | None,
    action_label: str,
) -> tuple[NotionSyncSourceScope | None, LineTrip | None, str | None]:
    chat_scope, error_message = _resolve_chat_scope(
        source=source,
        action_label=action_label,
    )
    if error_message is not None:
        return None, None, error_message
    if trip_repository is None:
        return None, None, TRIP_FEATURE_UNAVAILABLE_MESSAGE

    active_trip = trip_repository.get_active_trip(chat_scope)
    if active_trip is None:
        return None, None, TRIP_REQUIRED_MESSAGE

    trip_scope = build_source_scope(
        source_type=active_trip.source_type,
        group_id=active_trip.group_id,
        room_id=active_trip.room_id,
        user_id=active_trip.user_id,
        trip_id=active_trip.trip_id,
        trip_title=active_trip.title,
    )
    if trip_scope is None:
        return None, None, f"無法辨識目前聊天室，暫時無法{action_label}。"
    return trip_scope, active_trip, None


async def _run_notion_sync_command(
    *,
    repository: NotionSyncRepository | None,
    target_manager: NotionTargetManager,
    force: bool,
    source_scope: NotionSyncSourceScope | None,
    map_enrichment_repository: MapEnrichmentRepository | None,
    map_enrichment_service: LodgingMapEnrichmentService | None,
) -> str:
    if source_scope is None:
        return TRIP_REQUIRED_MESSAGE

    resolved_service = target_manager.resolve_service(source_scope)
    if repository is None or target_manager.default_service is None:
        return "Notion sync 尚未設定完成。"

    try:
        if force:
            resolved_service = await target_manager.setup_database(
                title=source_scope.trip_title,
                source_scope=(
                    source_scope
                    if source_scope.trip_id is not None
                    or (
                        resolved_service is not None
                        and resolved_service.target_source == "scoped"
                    )
                    else None
                ),
            )
            if (
                resolved_service is None
                or not resolved_service.service.is_sync_configured
            ):
                return "Notion sync 尚未設定完成。"
        elif resolved_service is None or not resolved_service.service.is_sync_configured:
            return "Notion sync 尚未設定完成。"
        await _run_lodging_enrichment_before_notion_sync(
            repository=map_enrichment_repository,
            service=map_enrichment_service,
            force=force,
            source_scope=source_scope,
        )
        summary = await run_notion_sync_job(
            repository=repository,
            service=resolved_service.service,
            limit=None,
            force=force,
            source_scope=source_scope,
            target_manager=target_manager,
        )
    except Exception:
        logger.exception("Failed to run Notion sync command from LINE.")
        action = "全部重來" if force else "整理"
        return f"Notion {action}失敗，請稍後再試。"

    return _format_notion_sync_summary(summary=summary, force=force)


async def _run_lodging_enrichment_before_notion_sync(
    *,
    repository: MapEnrichmentRepository | None,
    service: LodgingMapEnrichmentService | None,
    force: bool,
    source_scope: NotionSyncSourceScope,
) -> None:
    if repository is None or service is None:
        return

    if force:
        await retry_all_map_enrichment_documents(
            repository=repository,
            service=service,
            limit=None,
            source_scope=source_scope,
        )
        return

    await run_map_enrichment_job(
        repository=repository,
        service=service,
        limit=None,
        source_scope=source_scope,
    )


async def _run_automatic_notion_sync_after_capture(
    *,
    source_scope: NotionSyncSourceScope,
    notion_sync_repository: NotionSyncRepository | None,
    notion_target_manager: NotionTargetManager,
    map_enrichment_repository: MapEnrichmentRepository | None,
    map_enrichment_service: LodgingMapEnrichmentService | None,
) -> None:
    resolved_service = notion_target_manager.resolve_service(source_scope)
    if notion_sync_repository is None or resolved_service is None:
        return

    if not resolved_service.service.is_sync_configured:
        return

    try:
        await _run_lodging_enrichment_before_notion_sync(
            repository=map_enrichment_repository,
            service=map_enrichment_service,
            force=False,
            source_scope=source_scope,
        )
        await run_notion_sync_job(
            repository=notion_sync_repository,
            service=resolved_service.service,
            limit=None,
            force=False,
            source_scope=source_scope,
            target_manager=notion_target_manager,
        )
    except Exception:
        logger.exception("Failed to run automatic Notion sync after capture.")


async def _run_notion_list_command(
    *,
    settings: Settings,
    target_manager: NotionTargetManager,
    source_scope: NotionSyncSourceScope | None,
) -> str:
    if source_scope is None:
        return TRIP_REQUIRED_MESSAGE

    resolved_service = target_manager.resolve_service(source_scope)
    if source_scope.trip_id and resolved_service is None:
        return "目前旅次的 Notion 清單連結尚未設定完成。"
    notion_url: str | None = None
    if resolved_service is not None:
        if (
            resolved_service.target_source == "scoped"
            and resolved_service.target.share_url
        ):
            return str(resolved_service.target.share_url)
        if resolved_service.target_source == "default":
            notion_url = settings.notion_public_database_url.strip() or None
            if notion_url:
                return notion_url

        service = resolved_service.service
        try:
            notion_url = await service.get_database_url(prefer_public=True)
        except Exception:
            logger.exception("Failed to resolve Notion database URL from LINE.")
            notion_url = service.public_database_url or service.database_url or None

        if resolved_service.target_source == "default" and service.public_database_url:
            settings.notion_public_database_url = service.public_database_url
        if resolved_service.target_source == "default" and service.database_url:
            settings.notion_database_url = service.database_url

    if not notion_url:
        notion_url = settings.notion_public_database_url.strip() or None
    if not notion_url:
        notion_url = settings.notion_database_url.strip() or None

    if not notion_url:
        return "Notion 清單連結尚未設定完成。"
    return notion_url


def _format_help_message() -> str:
    command_lines = [
        f"{command}：{description}"
        for command, description in LINE_COMMAND_DESCRIPTIONS
    ]
    return (
        "旅次模式操作：\n"
        f"1. {TRIP_CREATE_COMMAND} 東京 2026\n"
        "2. 貼 Booking / Agoda / Airbnb 住宿連結\n"
        f"3. {NOTION_SYNC_PENDING_COMMAND} 同步目前旅次到 Notion\n"
        f"4. {NOTION_LIST_COMMAND} 查看目前旅次清單\n"
        "\n"
        "注意：沒有啟用中的旅次時，bot 不會收住宿連結。\n"
        "\n"
        "指令列表：\n"
        + "\n".join(command_lines)
    )


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
    try:
        return build_source_scope(
            source_type=source.type,
            group_id=source.groupId,
            room_id=source.roomId,
            user_id=source.userId,
        )
    except ValueError:
        return None


async def process_events(
    payload: LineWebhookRequest,
    settings: Settings,
    repository: CapturedLinkRepository,
    line_client: LineClient,
    lodging_link_service: LodgingLinkService,
    trip_repository: TripRepository | None = None,
    notion_sync_repository: NotionSyncRepository | None = None,
    notion_target_manager: NotionTargetManager | None = None,
    map_enrichment_repository: MapEnrichmentRepository | None = None,
    map_enrichment_service: LodgingMapEnrichmentService | None = None,
) -> int:
    active_notion_target_manager = notion_target_manager or NotionTargetManager(None)
    captured_total = 0

    for event in payload.events:
        event_type = event.type
        reply_token = event.replyToken

        if event_type == "join" and reply_token and settings.line_channel_access_token:
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
            trip_repository=trip_repository,
            notion_sync_repository=notion_sync_repository,
            notion_target_manager=active_notion_target_manager,
            map_enrichment_repository=map_enrichment_repository,
            map_enrichment_service=map_enrichment_service,
        ):
            continue

        extracted_matches = extract_lodging_links(text, settings.supported_domains)
        link_matches = await lodging_link_service.filter_supported_lodging_links(
            extracted_matches
        )
        if not link_matches:
            continue

        trip_scope, active_trip, trip_error_message = _resolve_active_trip_scope(
            source=event.source,
            trip_repository=trip_repository,
            action_label="收錄住宿連結",
        )
        if trip_error_message is not None:
            await _reply_if_possible(
                settings=settings,
                line_client=line_client,
                reply_token=reply_token,
                text=TRIP_CAPTURE_REQUIRED_MESSAGE
                if trip_error_message == TRIP_REQUIRED_MESSAGE
                else trip_error_message,
            )
            continue
        assert trip_scope is not None
        assert active_trip is not None

        records: list[CapturedLodgingLink] = []
        duplicate_reply_urls: list[str] = []
        seen_duplicate_reply_urls: set[str] = set()
        pending_lookup_urls: set[str] = set()

        for link in link_matches:
            lookup_urls = _build_duplicate_lookup_urls(link)
            if any(url in pending_lookup_urls for url in lookup_urls):
                reply_url = (
                    link.url
                    if _uses_short_link(
                        url=link.url,
                        resolved_url=link.resolved_url,
                    )
                    else link.resolved_url or link.url
                )
                if reply_url not in seen_duplicate_reply_urls:
                    duplicate_reply_urls.append(reply_url)
                    seen_duplicate_reply_urls.add(reply_url)
                continue

            duplicate = repository.find_duplicate(
                lookup_urls,
                source_type=event.source.type,
                trip_id=active_trip.trip_id,
                group_id=event.source.groupId,
                room_id=event.source.roomId,
                user_id=event.source.userId,
            )
            if duplicate is not None:
                reply_url = _select_duplicate_reply_url(
                    match=link,
                    duplicate=duplicate,
                )
                if reply_url not in seen_duplicate_reply_urls:
                    duplicate_reply_urls.append(reply_url)
                    seen_duplicate_reply_urls.add(reply_url)
                continue

            records.append(
                CapturedLodgingLink(
                    platform=link.platform,
                    url=link.url,
                    hostname=link.hostname,
                    resolved_url=link.resolved_url,
                    resolved_hostname=link.resolved_hostname,
                    message_text=text,
                    source_type=event.source.type,
                    destination=payload.destination,
                    trip_id=active_trip.trip_id,
                    trip_title=active_trip.title,
                    group_id=event.source.groupId,
                    room_id=event.source.roomId,
                    user_id=event.source.userId,
                    message_id=event.message.id,
                    event_timestamp_ms=event.timestamp,
                    event_mode=event.mode,
                )
            )
            pending_lookup_urls.update(lookup_urls)

        captured_count = repository.append_many(records) if records else 0
        captured_total += captured_count

        if captured_count > 0:
            await _run_automatic_notion_sync_after_capture(
                source_scope=trip_scope,
                notion_sync_repository=notion_sync_repository,
                notion_target_manager=active_notion_target_manager,
                map_enrichment_repository=map_enrichment_repository,
                map_enrichment_service=map_enrichment_service,
            )

        reply_messages = [
            settings.reply_duplicate_link_template.format(url=url)
            for url in duplicate_reply_urls
        ]
        if settings.line_reply_on_capture and captured_count > 0:
            reply_messages.append(
                settings.reply_capture_template.format(count=captured_count)
            )

        if reply_messages and reply_token and settings.line_channel_access_token:
            await _safe_reply(
                line_client,
                reply_token,
                "\n\n".join(reply_messages),
            )

    return captured_total
