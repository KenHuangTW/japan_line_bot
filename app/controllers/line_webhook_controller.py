from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

from app.config import Settings
from app.controllers.integration.line_client import LineClient
from app.controllers.repositories.captured_link_repository import CapturedLinkRepository
from app.controllers.repositories.trip_repository import TripRepository
from app.link_extractor import extract_lodging_links
from app.lodging_links import LodgingLinkService
from app.lodging_links.common import build_lodging_lookup_keys
from app.lodging_summary import (
    DecisionSummaryService,
    LodgingDecisionSummaryConfigurationError,
    LodgingDecisionSummaryEmptyTripError,
    LodgingDecisionSummaryError,
    build_line_lodging_decision_summary,
)
from app.map_enrichment import (
    LodgingMapEnrichmentService,
    MapEnrichmentRepository,
    MapEnrichmentSummary,
    retry_all_map_enrichment_documents,
    run_map_enrichment_job,
)
from app.models import (
    CapturedLodgingLink,
    LineTrip,
    LodgingDecisionStatus,
    LodgingLinkMatch,
)
from app.schemas.line_webhook import LineEventSource, LineWebhookRequest
from app.source_scope import SourceScope, build_source_scope
from app.trip_display import (
    TripDisplayFilters,
    TripDisplayRepository,
    build_line_trip_flex_message,
    build_line_trip_preview,
)

logger = logging.getLogger(__name__)

HELP_COMMAND = "/help"
PING_COMMAND = "/ping"
TRIP_CREATE_COMMAND = "/建立旅次"
TRIP_SWITCH_COMMAND = "/切換旅次"
TRIP_CURRENT_COMMAND = "/目前旅次"
TRIP_ARCHIVE_COMMAND = "/封存旅次"
TRIP_LIST_COMMAND = "/清單"
SUMMARY_COMMAND = "/摘要"
TRIP_REFRESH_COMMAND = "/整理"
TRIP_FORCE_REFRESH_COMMAND = "/全部重來"
TRIP_FEATURE_UNAVAILABLE_MESSAGE = "旅次功能尚未設定完成。"
TRIP_REQUIRED_MESSAGE = (
    "目前沒有啟用中的旅次，請先用 /建立旅次 <名稱> 建立，或用 /切換旅次 <名稱> 切換。"
)
TRIP_CAPTURE_REQUIRED_MESSAGE = (
    "請先建立或切換旅次，再貼住宿連結。用法：/建立旅次 <名稱> 或 /切換旅次 <名稱>"
)
SUMMARY_FEATURE_UNAVAILABLE_MESSAGE = "AI 摘要尚未設定完成。"
SUMMARY_EMPTY_TRIP_MESSAGE = "目前旅次還沒有住宿資料可摘要，請先貼住宿連結。"
SUMMARY_FAILED_MESSAGE = "目前無法產生住宿摘要，請稍後再試。"
LODGING_DECISION_FAILED_MESSAGE = "找不到這筆住宿，可能已不在目前旅次。"
LINE_COMMAND_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    (HELP_COMMAND, "顯示目前支援的指令與說明"),
    (PING_COMMAND, "回覆 pong"),
    (TRIP_CREATE_COMMAND, "建立新旅次並切換為目前旅次，格式：/建立旅次 <名稱>"),
    (TRIP_SWITCH_COMMAND, "切換到既有旅次，格式：/切換旅次 <名稱>"),
    (TRIP_CURRENT_COMMAND, "查看目前啟用中的旅次"),
    (TRIP_ARCHIVE_COMMAND, "封存目前旅次並清空 active trip"),
    (TRIP_LIST_COMMAND, "回傳目前旅次的住宿 preview 與詳情頁連結"),
    (SUMMARY_COMMAND, "產生目前旅次的 AI 決策摘要"),
    (
        TRIP_REFRESH_COMMAND,
        "整理目前旅次中尚未補齊的住宿與地圖資料",
    ),
    (
        TRIP_FORCE_REFRESH_COMMAND,
        "忽略既有整理狀態，重新整理目前旅次中的所有住宿與地圖資料",
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


async def _safe_reply_messages(
    line_client: LineClient,
    reply_token: str,
    messages: list[dict[str, Any]],
) -> bool:
    try:
        await line_client.reply_messages(reply_token, messages)
        return True
    except Exception:
        logger.exception("Failed to send LINE reply messages.")
        return False


async def _handle_line_command(
    *,
    text: str,
    source: LineEventSource,
    reply_token: str | None,
    settings: Settings,
    line_client: LineClient,
    trip_repository: TripRepository | None,
    trip_display_repository: TripDisplayRepository | None,
    decision_summary_service: DecisionSummaryService | None,
    trip_detail_url_builder: Callable[[str], str] | None,
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
                settings=settings,
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
                settings=settings,
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
                settings=settings,
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
                settings=settings,
                source=source,
                trip_repository=trip_repository,
            ),
        )
        return True

    if command == TRIP_LIST_COMMAND:
        _, active_trip, error_message = _resolve_command_active_trip_scope(
            settings=settings,
            source=source,
            trip_repository=trip_repository,
            action_label="查詢目前旅次",
        )
        if error_message is not None:
            await _reply_if_possible(
                settings=settings,
                line_client=line_client,
                reply_token=reply_token,
                text=error_message,
            )
            return True

        reply_messages, fallback_text = _build_trip_list_reply(
            active_trip=active_trip,
            trip_display_repository=trip_display_repository,
            trip_detail_url_builder=trip_detail_url_builder,
        )
        if reply_messages is not None:
            await _reply_messages_if_possible(
                settings=settings,
                line_client=line_client,
                reply_token=reply_token,
                messages=reply_messages,
                fallback_text=fallback_text,
            )
        else:
            await _reply_if_possible(
                settings=settings,
                line_client=line_client,
                reply_token=reply_token,
                text=fallback_text,
            )
        return True

    if command == SUMMARY_COMMAND:
        _, active_trip, error_message = _resolve_command_active_trip_scope(
            settings=settings,
            source=source,
            trip_repository=trip_repository,
            action_label="產生旅次摘要",
        )
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=(
                error_message
                if error_message is not None
                else await _run_decision_summary_command(
                    active_trip=active_trip,
                    decision_summary_service=decision_summary_service,
                )
            ),
        )
        return True

    if command == TRIP_REFRESH_COMMAND:
        trip_scope, _, error_message = _resolve_command_active_trip_scope(
            settings=settings,
            source=source,
            trip_repository=trip_repository,
            action_label="整理旅次資料",
        )
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=(
                error_message
                if error_message is not None
                else await _run_trip_refresh_command(
                    force=False,
                    source_scope=trip_scope,
                    map_enrichment_repository=map_enrichment_repository,
                    map_enrichment_service=map_enrichment_service,
                )
            ),
        )
        return True

    if command == TRIP_FORCE_REFRESH_COMMAND:
        trip_scope, _, error_message = _resolve_command_active_trip_scope(
            settings=settings,
            source=source,
            trip_repository=trip_repository,
            action_label="重新整理旅次資料",
        )
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=(
                error_message
                if error_message is not None
                else await _run_trip_refresh_command(
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


async def _reply_messages_if_possible(
    *,
    settings: Settings,
    line_client: LineClient,
    reply_token: str | None,
    messages: list[dict[str, Any]],
    fallback_text: str | None = None,
) -> None:
    if reply_token and settings.line_channel_access_token:
        sent = await _safe_reply_messages(line_client, reply_token, messages)
        if not sent and fallback_text:
            await _safe_reply(line_client, reply_token, fallback_text)


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
    settings: Settings,
    source: LineEventSource,
    title: str | None,
    trip_repository: TripRepository | None,
) -> str:
    chat_scope, error_message = _resolve_command_chat_scope(
        settings=settings,
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
        switched_trip = trip_repository.switch_active_trip(
            chat_scope, existing_trip.title
        )
        if switched_trip is None:
            return f"找不到旅次：{existing_trip.title}"
        return f"旅次已存在，已切換到：{switched_trip.title}"

    trip = trip_repository.create_trip(chat_scope, title)
    return f"已建立並切換到旅次：{trip.title}"


def _run_trip_switch_command(
    *,
    settings: Settings,
    source: LineEventSource,
    title: str | None,
    trip_repository: TripRepository | None,
) -> str:
    chat_scope, error_message = _resolve_command_chat_scope(
        settings=settings,
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
    settings: Settings,
    source: LineEventSource,
    trip_repository: TripRepository | None,
) -> str:
    _, trip, error_message = _resolve_command_active_trip_scope(
        settings=settings,
        source=source,
        trip_repository=trip_repository,
        action_label="查詢目前旅次",
    )
    if error_message is not None:
        return error_message
    assert trip is not None
    return f"目前旅次：{trip.title}\n" f"旅次 ID：{trip.trip_id}\n" "狀態：進行中"


def _run_trip_archive_command(
    *,
    settings: Settings,
    source: LineEventSource,
    trip_repository: TripRepository | None,
) -> str:
    chat_scope, error_message = _resolve_command_chat_scope(
        settings=settings,
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
) -> tuple[SourceScope | None, str | None]:
    source_scope = _build_source_scope(source)
    if source_scope is None:
        return None, f"無法辨識目前聊天室，暫時無法{action_label}。"
    return source_scope, None


def _resolve_command_chat_scope(
    *,
    settings: Settings,
    source: LineEventSource,
    action_label: str,
) -> tuple[SourceScope | None, str | None]:
    return _resolve_chat_scope(
        source=_resolve_target_source(settings=settings, source=source),
        action_label=action_label,
    )


def _resolve_active_trip_scope(
    *,
    source: LineEventSource,
    trip_repository: TripRepository | None,
    action_label: str,
) -> tuple[SourceScope | None, LineTrip | None, str | None]:
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


def _resolve_command_active_trip_scope(
    *,
    settings: Settings,
    source: LineEventSource,
    trip_repository: TripRepository | None,
    action_label: str,
) -> tuple[SourceScope | None, LineTrip | None, str | None]:
    return _resolve_active_trip_scope(
        source=_resolve_target_source(settings=settings, source=source),
        trip_repository=trip_repository,
        action_label=action_label,
    )


async def _run_trip_refresh_command(
    *,
    force: bool,
    source_scope: SourceScope | None,
    map_enrichment_repository: MapEnrichmentRepository | None,
    map_enrichment_service: LodgingMapEnrichmentService | None,
) -> str:
    if source_scope is None:
        return TRIP_REQUIRED_MESSAGE
    if map_enrichment_repository is None or map_enrichment_service is None:
        return "住宿整理功能尚未設定完成。"

    try:
        summary = await _run_lodging_enrichment_for_trip(
            repository=map_enrichment_repository,
            service=map_enrichment_service,
            force=force,
            source_scope=source_scope,
        )
    except Exception:
        logger.exception("Failed to run trip refresh command from LINE.")
        return "旅次資料整理失敗，請稍後再試。"

    return _format_trip_refresh_summary(summary=summary, force=force)


async def _run_lodging_enrichment_for_trip(
    *,
    repository: MapEnrichmentRepository | None,
    service: LodgingMapEnrichmentService | None,
    force: bool,
    source_scope: SourceScope,
) -> Any:
    if repository is None or service is None:
        raise RuntimeError("Map enrichment is not configured.")

    if force:
        return await retry_all_map_enrichment_documents(
            repository=repository,
            service=service,
            limit=None,
            source_scope=source_scope,
        )

    return await run_map_enrichment_job(
        repository=repository,
        service=service,
        limit=None,
        source_scope=source_scope,
    )


def _build_trip_list_reply(
    *,
    active_trip: LineTrip | None,
    trip_display_repository: TripDisplayRepository | None,
    trip_detail_url_builder: Callable[[str], str] | None,
) -> tuple[list[dict[str, Any]] | None, str]:
    if active_trip is None:
        return None, TRIP_REQUIRED_MESSAGE
    if trip_display_repository is None or trip_detail_url_builder is None:
        return None, "旅次顯示頁尚未設定完成。"

    surface = trip_display_repository.build_trip_display(
        active_trip,
        TripDisplayFilters(),
    )
    detail_url = trip_detail_url_builder(active_trip.display_token)
    return [
        build_line_trip_flex_message(
            surface,
            detail_url=detail_url,
        )
    ], build_line_trip_preview(
        surface,
        detail_url=detail_url,
    )


def _format_help_message() -> str:
    command_lines = [
        f"{command}：{description}"
        for command, description in LINE_COMMAND_DESCRIPTIONS
    ]
    return (
        "旅次模式操作：\n"
        f"1. {TRIP_CREATE_COMMAND} 東京 2026\n"
        "2. 貼 Booking / Agoda / Airbnb 住宿連結\n"
        f"3. {TRIP_REFRESH_COMMAND} 整理目前旅次資料\n"
        f"4. {TRIP_LIST_COMMAND} 查看目前旅次清單\n"
        f"5. {SUMMARY_COMMAND} 產生 AI 決策摘要\n"
        "\n"
        "注意：沒有啟用中的旅次時，bot 不會收住宿連結。\n"
        "\n"
        "指令列表：\n" + "\n".join(command_lines)
    )


async def _run_decision_summary_command(
    *,
    active_trip: LineTrip | None,
    decision_summary_service: DecisionSummaryService | None,
) -> str:
    if active_trip is None:
        return TRIP_REQUIRED_MESSAGE
    if decision_summary_service is None:
        return SUMMARY_FEATURE_UNAVAILABLE_MESSAGE

    try:
        result = await decision_summary_service.summarize_trip(active_trip)
    except LodgingDecisionSummaryConfigurationError:
        return SUMMARY_FEATURE_UNAVAILABLE_MESSAGE
    except LodgingDecisionSummaryEmptyTripError:
        return SUMMARY_EMPTY_TRIP_MESSAGE
    except LodgingDecisionSummaryError as exc:
        logger.warning(
            "Failed to generate lodging decision summary: %s: %s",
            exc.__class__.__name__,
            exc,
        )
        return SUMMARY_FAILED_MESSAGE
    except Exception:
        logger.exception("Unexpected lodging decision summary failure.")
        return SUMMARY_FAILED_MESSAGE

    return build_line_lodging_decision_summary(result)


def _format_trip_refresh_summary(
    *,
    summary: MapEnrichmentSummary,
    force: bool,
) -> str:
    action = "全部重來" if force else "整理"
    return (
        f"旅次資料{action}完成："
        f"處理 {summary.processed} 筆，"
        f"完整解析 {summary.resolved} 筆，"
        f"部分更新 {summary.partial} 筆，"
        f"失敗 {summary.failed} 筆。"
    )


def _build_source_scope(source: LineEventSource) -> SourceScope | None:
    try:
        return build_source_scope(
            source_type=source.type,
            group_id=source.groupId,
            room_id=source.roomId,
            user_id=source.userId,
        )
    except ValueError:
        return None


def _resolve_target_source(
    *,
    settings: Settings,
    source: LineEventSource,
) -> LineEventSource:
    (
        source_type,
        group_id,
        room_id,
        user_id,
    ) = settings.resolve_line_target_source(
        source_type=source.type,
        group_id=source.groupId,
        room_id=source.roomId,
        user_id=source.userId,
    )
    if (
        source_type == source.type
        and group_id == source.groupId
        and room_id == source.roomId
        and user_id == source.userId
    ):
        return source

    return LineEventSource(
        type=source_type,
        groupId=group_id,
        roomId=room_id,
        userId=user_id,
    )


async def _handle_line_postback(
    *,
    data: str,
    source: LineEventSource,
    reply_token: str | None,
    settings: Settings,
    line_client: LineClient,
    repository: CapturedLinkRepository,
    trip_repository: TripRepository | None,
) -> bool:
    params = parse_qs(data, keep_blank_values=True)
    action = _first_postback_value(params, "action")
    if action != "lodging_decision":
        return False

    decision_status = _parse_lodging_decision_status(
        _first_postback_value(params, "decision_status")
    )
    document_id = _first_postback_value(params, "document_id")
    if decision_status is None or not document_id:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=LODGING_DECISION_FAILED_MESSAGE,
        )
        return True

    target_source = _resolve_target_source(settings=settings, source=source)
    _, active_trip, error_message = _resolve_active_trip_scope(
        source=target_source,
        trip_repository=trip_repository,
        action_label="更新住宿狀態",
    )
    if error_message is not None:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=error_message,
        )
        return True

    assert active_trip is not None
    lodging = repository.update_decision_status(
        document_id,
        decision_status=decision_status,
        source_type=target_source.type,
        trip_id=active_trip.trip_id,
        group_id=target_source.groupId,
        room_id=target_source.roomId,
        user_id=target_source.userId,
        updated_by_user_id=source.userId,
    )
    if lodging is None:
        await _reply_if_possible(
            settings=settings,
            line_client=line_client,
            reply_token=reply_token,
            text=LODGING_DECISION_FAILED_MESSAGE,
        )
        return True

    await _reply_if_possible(
        settings=settings,
        line_client=line_client,
        reply_token=reply_token,
        text=_format_lodging_decision_reply(
            lodging=lodging,
            decision_status=decision_status,
        ),
    )
    return True


def _first_postback_value(
    params: dict[str, list[str]],
    key: str,
) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0].strip() or None


def _parse_lodging_decision_status(value: str | None) -> LodgingDecisionStatus | None:
    if value in {"candidate", "booked", "dismissed"}:
        return value  # type: ignore[return-value]
    return None


def _format_lodging_decision_reply(
    *,
    lodging: CapturedLodgingLink,
    decision_status: LodgingDecisionStatus,
) -> str:
    display_name = lodging.property_name or lodging.resolved_url or lodging.url
    if decision_status == "booked":
        return f"已標記為已預訂：{display_name}"
    if decision_status == "dismissed":
        return f"已移出候選：{display_name}"
    return f"已改回候選：{display_name}"


async def process_events(
    payload: LineWebhookRequest,
    settings: Settings,
    repository: CapturedLinkRepository,
    line_client: LineClient,
    lodging_link_service: LodgingLinkService,
    trip_repository: TripRepository | None = None,
    trip_display_repository: TripDisplayRepository | None = None,
    decision_summary_service: DecisionSummaryService | None = None,
    map_enrichment_repository: MapEnrichmentRepository | None = None,
    map_enrichment_service: LodgingMapEnrichmentService | None = None,
    trip_detail_url_builder: Callable[[str], str] | None = None,
) -> int:
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

        if event_type == "postback":
            handled = await _handle_line_postback(
                data=event.postback.data,
                source=event.source,
                reply_token=reply_token,
                settings=settings,
                line_client=line_client,
                repository=repository,
                trip_repository=trip_repository,
            )
            if handled:
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
            trip_display_repository=trip_display_repository,
            decision_summary_service=decision_summary_service,
            trip_detail_url_builder=trip_detail_url_builder,
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

        target_source = _resolve_target_source(settings=settings, source=event.source)
        trip_scope, active_trip, trip_error_message = _resolve_active_trip_scope(
            source=target_source,
            trip_repository=trip_repository,
            action_label="收錄住宿連結",
        )
        if trip_error_message is not None:
            await _reply_if_possible(
                settings=settings,
                line_client=line_client,
                reply_token=reply_token,
                text=(
                    TRIP_CAPTURE_REQUIRED_MESSAGE
                    if trip_error_message == TRIP_REQUIRED_MESSAGE
                    else trip_error_message
                ),
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
                source_type=target_source.type,
                trip_id=active_trip.trip_id,
                group_id=target_source.groupId,
                room_id=target_source.roomId,
                user_id=target_source.userId,
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
                    source_type=target_source.type,
                    destination=payload.destination,
                    trip_id=active_trip.trip_id,
                    trip_title=active_trip.title,
                    group_id=target_source.groupId,
                    room_id=target_source.roomId,
                    user_id=target_source.userId,
                    message_id=event.message.id,
                    event_timestamp_ms=event.timestamp,
                    event_mode=event.mode,
                )
            )
            pending_lookup_urls.update(lookup_urls)

        captured_count = repository.append_many(records) if records else 0
        captured_total += captured_count

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
