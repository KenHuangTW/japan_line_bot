from __future__ import annotations

from collections import Counter, defaultdict
from datetime import time
from typing import Sequence

from app.itinerary.service import ItineraryApplyResult, ItineraryDraftResult
from app.models import ItineraryDraft, ItineraryItem

MAX_LINE_MESSAGE_LENGTH = 4500


def build_itinerary_draft_reply(result: ItineraryDraftResult) -> str:
    counts = Counter(change.action for change in result.draft.changes)
    lines = [
        f"已整理行程草稿：{result.source.trip_title or result.source.trip_id}",
        (
            f"新增 {counts['add']} 筆，"
            f"更新 {counts['update']} 筆，"
            f"可能刪除 {counts['possible_delete']} 筆，"
            f"不變 {counts['unchanged']} 筆。"
        ),
    ]
    if result.draft.day_notes:
        lines.append(f"另保留 {len(result.draft.day_notes)} 則每日備註。")
    lines.append("確認後請輸入 /套用行程；不套用請輸入 /取消行程。")
    preview = _build_draft_preview(result.draft)
    if preview:
        lines.extend(["", preview])
    return _truncate("\n".join(lines))


def build_itinerary_apply_reply(result: ItineraryApplyResult) -> str:
    return (
        "行程已套用："
        f"新增 {result.added} 筆，"
        f"更新 {result.updated} 筆，"
        f"取消 {result.cancelled} 筆，"
        f"不變 {result.unchanged} 筆。"
    )


def build_itinerary_discard_reply(_: ItineraryDraft) -> str:
    return "已取消這次行程草稿，正式行程沒有變更。"


def build_itinerary_list_reply(
    *,
    trip_title: str,
    items: Sequence[ItineraryItem],
) -> str:
    if not items:
        return "目前旅次還沒有正式行程。可以貼行程文字，或回覆既有行程訊息輸入 /整理行程。"

    grouped: dict[str, list[ItineraryItem]] = defaultdict(list)
    for item in items:
        grouped[item.date.isoformat()].append(item)

    lines = [f"目前行程：{trip_title}"]
    for item_date in sorted(grouped):
        lines.append("")
        lines.append(item_date)
        for item in grouped[item_date]:
            time_label = _format_time_range(item.start_time, item.end_time)
            status_label = _status_label(item.status)
            location = f"｜{item.location_name}" if item.location_name else ""
            lines.append(f"- {time_label} {item.title}{location}（{status_label}）")
    return _truncate("\n".join(lines))


def _build_draft_preview(draft: ItineraryDraft) -> str:
    preview_lines: list[str] = []
    for change in draft.changes[:8]:
        item = change.proposed_item or change.existing_item
        if item is None:
            continue
        action_label = {
            "add": "+",
            "update": "~",
            "possible_delete": "-",
            "unchanged": "=",
        }[change.action]
        preview_lines.append(
            f"{action_label} {item.date.isoformat()} "
            f"{_format_time_range(item.start_time, item.end_time)} {item.title}"
        )
    if len(draft.changes) > len(preview_lines):
        preview_lines.append(f"...另有 {len(draft.changes) - len(preview_lines)} 筆")
    return "\n".join(preview_lines)


def _format_time_range(start: time | None, end: time | None) -> str:
    if start is None:
        return "未定"
    if end is None:
        return start.strftime("%H:%M")
    return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _status_label(status: str) -> str:
    return {
        "confirmed": "確定",
        "tentative": "待確認",
        "optional": "可選",
        "cancelled": "已取消",
    }.get(status, status)


def _truncate(value: str) -> str:
    if len(value) <= MAX_LINE_MESSAGE_LENGTH:
        return value
    return f"{value[: MAX_LINE_MESSAGE_LENGTH - 1].rstrip()}…"
