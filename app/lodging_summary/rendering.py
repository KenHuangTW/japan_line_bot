from __future__ import annotations

from app.lodging_summary.service import LodgingDecisionSummaryResult
from app.schemas.lodging_summary import LodgingDecisionSummaryLodging

MAX_LINE_LENGTH = 120
MAX_MESSAGE_LENGTH = 4500

PLATFORM_LABELS = {
    "booking": "Booking.com",
    "agoda": "Agoda",
    "airbnb": "Airbnb",
}

AVAILABILITY_LABELS = {
    "available": "可訂",
    "sold_out": "已售完",
    "unknown": "待確認",
}


def build_line_lodging_decision_summary(
    result: LodgingDecisionSummaryResult,
) -> str:
    lodging_by_id = {
        lodging.document_id: lodging for lodging in result.request.lodgings
    }
    lines = [
        f"目前旅次摘要：{result.request.trip.title}",
        (
            "候選住宿 "
            f"{result.request.summary.total_lodgings} 筆"
            f"（可訂 {result.request.summary.available_count}"
            f" / 已售完 {result.request.summary.sold_out_count}"
            f" / 待確認 {result.request.summary.unknown_count}）"
        ),
        "",
        "優先候選",
    ]

    for index, candidate in enumerate(result.response.top_candidates, start=1):
        lodging = lodging_by_id[candidate.document_id]
        lines.append(f"{index}. {lodging.display_name}")
        lines.append(_format_lodging_meta(lodging))
        lines.append(f"- {_truncate(candidate.reason)}")

    lines.extend(_format_section("優點", result.response.pros))
    lines.extend(_format_section("缺點", result.response.cons))
    lines.extend(
        _format_section("待補資訊", result.response.missing_information)
    )
    lines.extend(
        _format_section("討論重點", result.response.discussion_points)
    )
    return _truncate_message("\n".join(lines).strip())


def _format_section(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return ["", title, *[f"- {_truncate(item)}" for item in items]]


def _format_lodging_meta(lodging: LodgingDecisionSummaryLodging) -> str:
    platform = PLATFORM_LABELS.get(lodging.platform.lower(), lodging.platform)
    availability = AVAILABILITY_LABELS[lodging.availability]
    details = [platform]
    if lodging.price_amount is not None and lodging.price_currency:
        details.append(f"{lodging.price_currency} {lodging.price_amount:,.0f}")
    else:
        details.append("價格待確認")
    details.append(availability)
    if lodging.city:
        details.append(lodging.city)
    return "｜".join(details)


def _truncate(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= MAX_LINE_LENGTH:
        return normalized
    return f"{normalized[: MAX_LINE_LENGTH - 1].rstrip()}…"


def _truncate_message(value: str) -> str:
    if len(value) <= MAX_MESSAGE_LENGTH:
        return value
    return f"{value[: MAX_MESSAGE_LENGTH - 1].rstrip()}…"
