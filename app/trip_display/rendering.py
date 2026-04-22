from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlencode

from app.line_media import normalize_line_uri
from app.trip_display.models import (
    TripDisplayFilters,
    TripDisplayLodging,
    TripDisplaySurface,
)

PLATFORM_LABELS = {
    "booking": "Booking.com",
    "agoda": "Agoda",
    "airbnb": "Airbnb",
}

SORT_LABELS = {
    "captured_desc": "最新收錄",
    "captured_asc": "最早收錄",
    "price_asc": "價格由低到高",
    "price_desc": "價格由高到低",
}

AVAILABILITY_LABELS = {
    "all": "全部狀態",
    "available": "可訂",
    "sold_out": "已售完",
    "unknown": "待確認",
}

DECISION_STATUS_LABELS = {
    "active": "顯示中",
    "all": "全部決策",
    "candidate": "候選中",
    "booked": "已預訂",
    "dismissed": "不考慮",
}


def build_line_trip_preview(
    surface: TripDisplaySurface,
    *,
    detail_url: str,
    preview_limit: int = 3,
) -> str:
    lines = [
        f"目前旅次：{surface.trip_title}",
        (
            f"住宿 {surface.total_lodgings} 筆"
            f"（已訂 {surface.booked_count} / 候選 {surface.candidate_count} / 不考慮 {surface.dismissed_count}）"
        ),
    ]

    preview_items = surface.lodgings[:preview_limit]
    if preview_items:
        for index, lodging in enumerate(preview_items, start=1):
            lines.extend(
                [
                    f"{index}. {lodging.display_name}",
                    (
                        f"{platform_label(lodging.platform)}｜"
                        f"{lodging.price_label}｜{lodging.availability_label}｜"
                        f"{lodging.decision_status_label}"
                    ),
                ]
            )
    else:
        lines.append("目前還沒有候選住宿，先貼 Booking / Agoda / Airbnb 連結進來。")

    if surface.visible_count > preview_limit:
        lines.append(
            f"還有 {surface.visible_count - preview_limit} 筆，請到旅次頁查看完整清單。"
        )

    lines.extend(
        [
            "",
            f"旅次詳情：{detail_url}",
        ]
    )
    if surface.notion_export_url:
        lines.append(f"Notion 匯出：{surface.notion_export_url}")
    return "\n".join(lines)


def build_line_trip_flex_message(
    surface: TripDisplaySurface,
    *,
    detail_url: str,
    preview_limit: int = 5,
) -> dict[str, Any]:
    preview_items = surface.lodgings[:preview_limit]
    if preview_items:
        bubbles = [
            _build_flex_lodging_bubble(
                surface=surface,
                lodging=lodging,
                detail_url=detail_url,
                index=index,
                total=min(surface.visible_count, preview_limit),
            )
            for index, lodging in enumerate(preview_items, start=1)
        ]
    else:
        bubbles = [_build_empty_flex_bubble(surface=surface, detail_url=detail_url)]

    return {
        "type": "flex",
        "altText": build_line_trip_flex_alt_text(surface),
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }


def build_line_trip_flex_alt_text(surface: TripDisplaySurface) -> str:
    return (
        f"{surface.trip_title}：已訂 {surface.booked_count} 筆，"
        f"候選 {surface.candidate_count} 筆，"
        "請開啟旅次詳情查看完整清單。"
    )


def build_trip_detail_html(
    surface: TripDisplaySurface,
    *,
    request_path: str,
) -> str:
    cards = (
        "\n".join(_build_lodging_cards(surface.lodgings, request_path=request_path))
        or _build_empty_state()
    )
    notion_link = (
        (
            '<a class="secondary-link"'
            f' href="{escape(surface.notion_export_url, quote=True)}"'
            ' target="_blank" rel="noreferrer">開啟 Notion 匯出</a>'
        )
        if surface.notion_export_url
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(surface.trip_title)} | Trip Display</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f7f1e7;
        --bg-accent: #efe3d2;
        --card: rgba(255, 251, 246, 0.92);
        --ink: #1f2a32;
        --muted: #5f6b73;
        --line: rgba(31, 42, 50, 0.12);
        --accent: #156b6c;
        --accent-soft: rgba(21, 107, 108, 0.12);
        --warn: #9f5b00;
        --danger: #8c2f39;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Avenir Next", "Hiragino Sans CNS", "PingFang TC", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(255,255,255,0.6), transparent 38%),
          linear-gradient(180deg, var(--bg) 0%, #f3eadf 100%);
        color: var(--ink);
      }}
      main {{
        max-width: 960px;
        margin: 0 auto;
        padding: 20px 16px 56px;
      }}
      .hero {{
        padding: 22px;
        border: 1px solid var(--line);
        border-radius: 24px;
        background: linear-gradient(135deg, rgba(255,255,255,0.88), rgba(239,227,210,0.95));
        box-shadow: 0 18px 60px rgba(55, 41, 23, 0.08);
      }}
      .eyebrow {{
        margin: 0 0 8px;
        color: var(--accent);
        font-size: 0.82rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 0;
        font-family: "Iowan Old Style", "Times New Roman", serif;
        font-size: clamp(1.8rem, 5vw, 3rem);
        line-height: 1.05;
      }}
      .summary {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 18px;
      }}
      .metric {{
        padding: 10px 14px;
        border-radius: 999px;
        background: var(--card);
        border: 1px solid var(--line);
        color: var(--muted);
        font-size: 0.92rem;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 18px;
      }}
      .secondary-link {{
        display: inline-flex;
        align-items: center;
        padding: 10px 14px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.72);
        color: var(--ink);
        text-decoration: none;
      }}
      form {{
        margin-top: 18px;
        padding: 16px;
        border-radius: 20px;
        background: var(--card);
        border: 1px solid var(--line);
      }}
      .controls {{
        display: grid;
        gap: 12px;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      }}
      label {{
        display: grid;
        gap: 6px;
        font-size: 0.9rem;
        color: var(--muted);
      }}
      select {{
        width: 100%;
        padding: 11px 12px;
        border-radius: 14px;
        border: 1px solid var(--line);
        background: #fffdfa;
        color: var(--ink);
      }}
      .form-actions {{
        display: flex;
        gap: 10px;
        margin-top: 14px;
      }}
      button, .reset-link {{
        display: inline-flex;
        justify-content: center;
        align-items: center;
        min-height: 42px;
        padding: 0 16px;
        border-radius: 999px;
        border: none;
        text-decoration: none;
        cursor: pointer;
        font-size: 0.95rem;
      }}
      button {{
        background: var(--accent);
        color: white;
      }}
      .reset-link {{
        border: 1px solid var(--line);
        color: var(--ink);
        background: rgba(255,255,255,0.72);
      }}
      .grid {{
        display: grid;
        gap: 14px;
        margin-top: 18px;
      }}
      .card {{
        display: grid;
        grid-template-columns: minmax(180px, 30%) 1fr;
        overflow: hidden;
        padding: 0;
        border-radius: 22px;
        border: 1px solid var(--line);
        background: var(--card);
        box-shadow: 0 18px 42px rgba(48, 32, 18, 0.05);
      }}
      .card-media {{
        min-height: 188px;
        border-right: 1px solid var(--line);
        background: linear-gradient(135deg, rgba(233,244,241,0.95), rgba(255,253,250,0.82));
      }}
      .card-media-link,
      .card-thumbnail-fallback {{
        display: flex;
        width: 100%;
        height: 100%;
        min-height: 188px;
        aspect-ratio: 4 / 3;
      }}
      .card-media-link {{
        align-items: stretch;
        color: inherit;
        text-decoration: none;
      }}
      .card-thumbnail {{
        display: block;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }}
      .card-thumbnail-fallback {{
        flex-direction: column;
        justify-content: center;
        gap: 8px;
        padding: 18px;
        color: var(--muted);
      }}
      .card-fallback-platform {{
        color: var(--accent);
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
      }}
      .card-fallback-text {{
        font-size: 0.95rem;
        line-height: 1.4;
      }}
      .card-content {{
        min-width: 0;
        padding: 18px;
      }}
      .card-header {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: start;
      }}
      .card-title {{
        margin: 0;
        font-size: 1.1rem;
        line-height: 1.3;
      }}
      .chip-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 10px;
      }}
      .chip {{
        display: inline-flex;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--accent);
        font-size: 0.84rem;
      }}
      .chip.warn {{ background: rgba(159, 91, 0, 0.12); color: var(--warn); }}
      .chip.danger {{ background: rgba(140, 47, 57, 0.12); color: var(--danger); }}
      .meta {{
        margin: 12px 0 0;
        color: var(--muted);
        line-height: 1.5;
      }}
      .links {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 16px;
      }}
      .links a {{
        color: var(--accent);
        text-decoration: none;
      }}
      .decision-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 16px;
      }}
      .decision-actions form {{
        margin: 0;
        padding: 0;
        border: 0;
        background: transparent;
      }}
      .decision-actions button {{
        min-height: 38px;
      }}
      .decision-actions .secondary {{
        border: 1px solid var(--line);
        background: rgba(255,255,255,0.72);
        color: var(--ink);
      }}
      .empty {{
        padding: 36px 18px;
        text-align: center;
        border-radius: 22px;
        border: 1px dashed var(--line);
        background: rgba(255,255,255,0.48);
        color: var(--muted);
      }}
      @media (max-width: 640px) {{
        main {{ padding-inline: 12px; }}
        .hero, form, .card {{ border-radius: 18px; }}
        .card {{
          grid-template-columns: 1fr;
        }}
        .card-media {{
          border-right: 0;
          border-bottom: 1px solid var(--line);
        }}
        .card-media-link,
        .card-thumbnail-fallback {{
          min-height: 170px;
        }}
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <p class="eyebrow">Trip Display Surface</p>
        <h1>{escape(surface.trip_title)}</h1>
        <div class="summary">
          <span class="metric">顯示 {surface.visible_count} / {surface.total_lodgings} 筆</span>
          <span class="metric">已訂 {surface.booked_count}</span>
          <span class="metric">候選 {surface.candidate_count}</span>
          <span class="metric">不考慮 {surface.dismissed_count}</span>
          <span class="metric">可訂 {surface.available_count}</span>
          <span class="metric">已售完 {surface.sold_out_count}</span>
          <span class="metric">待確認 {surface.unknown_count}</span>
        </div>
        <div class="actions">
          {notion_link}
        </div>
      </section>
      <form method="get" action="{escape(request_path, quote=True)}">
        <div class="controls">
          <label>
            平台
            <select name="platform">
              {_build_platform_options(surface)}
            </select>
          </label>
          <label>
            狀態
            <select name="availability">
              {_build_availability_options(surface.filters)}
            </select>
          </label>
          <label>
            決策
            <select name="decision_status">
              {_build_decision_status_options(surface.filters)}
            </select>
          </label>
          <label>
            排序
            <select name="sort">
              {_build_sort_options(surface.filters)}
            </select>
          </label>
        </div>
        <div class="form-actions">
          <button type="submit">套用</button>
          <a class="reset-link" href="{escape(request_path, quote=True)}">重設</a>
        </div>
      </form>
      <section class="grid">
        {cards}
      </section>
    </main>
  </body>
</html>"""


def platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform.lower(), platform or "未知平台")


def _build_flex_lodging_bubble(
    *,
    surface: TripDisplaySurface,
    lodging: TripDisplayLodging,
    detail_url: str,
    index: int,
    total: int,
) -> dict[str, Any]:
    source_url = normalize_line_uri(lodging.target_url)
    trip_detail_url = normalize_line_uri(detail_url)
    bubble: dict[str, Any] = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "backgroundColor": "#E9F4F1",
            "contents": [
                {
                    "type": "text",
                    "text": surface.trip_title,
                    "size": "xs",
                    "color": "#156B6C",
                    "weight": "bold",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": f"{index}/{total}",
                    "size": "xs",
                    "color": "#5F6B73",
                    "margin": "sm",
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": lodging.display_name,
                    "weight": "bold",
                    "size": "lg",
                    "wrap": True,
                    **(
                        {"action": {"type": "uri", "uri": source_url}}
                        if source_url
                        else {}
                    ),
                },
                {
                    "type": "text",
                    "text": platform_label(lodging.platform),
                    "size": "sm",
                    "color": "#156B6C",
                    "weight": "bold",
                },
                {
                    "type": "box",
                    "layout": "baseline",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": lodging.price_label,
                            "wrap": True,
                            "size": "sm",
                            "color": "#1F2A32",
                            "flex": 4,
                        },
                        {
                            "type": "text",
                            "text": lodging.availability_label,
                            "wrap": True,
                            "size": "sm",
                            "color": _flex_status_color(lodging),
                            "align": "end",
                            "flex": 2,
                            "weight": "bold",
                        },
                    ],
                },
                {
                    "type": "text",
                    "text": lodging.decision_status_label,
                    "size": "sm",
                    "color": _flex_decision_color(lodging),
                    "weight": "bold",
                    "wrap": True,
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": _build_bubble_footer_contents(
                lodging=lodging,
                detail_url=trip_detail_url,
            ),
        },
    }
    if lodging.formatted_address:
        bubble["body"]["contents"].append(
            {
                "type": "text",
                "text": lodging.formatted_address,
                "size": "sm",
                "color": "#5F6B73",
                "wrap": True,
            }
        )
    hero_image_url = lodging.line_hero_image_url
    if hero_image_url and source_url:
        bubble["hero"] = {
            "type": "image",
            "url": hero_image_url,
            "size": "full",
            "aspectMode": "cover",
            "aspectRatio": "20:13",
            "action": {
                "type": "uri",
                "uri": source_url,
            },
        }
    return bubble


def _build_empty_flex_bubble(
    *,
    surface: TripDisplaySurface,
    detail_url: str,
) -> dict[str, Any]:
    trip_detail_url = normalize_line_uri(detail_url)
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "backgroundColor": "#E9F4F1",
            "contents": [
                {
                    "type": "text",
                    "text": surface.trip_title,
                    "size": "xs",
                    "color": "#156B6C",
                    "weight": "bold",
                    "wrap": True,
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": "目前還沒有候選住宿",
                    "weight": "bold",
                    "size": "lg",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": "先貼 Booking / Agoda / Airbnb 連結進來，這裡就會出現一張張房源卡片。",
                    "size": "sm",
                    "color": "#5F6B73",
                    "wrap": True,
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#156B6C",
                    "action": {
                        "type": "uri",
                        "label": "開啟旅次詳情",
                        "uri": trip_detail_url or detail_url,
                    },
                }
            ],
        },
    }


def _build_bubble_footer_contents(
    *,
    lodging: TripDisplayLodging,
    detail_url: str | None,
) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    postback_action = _build_decision_postback_action(lodging)
    if postback_action is not None:
        contents.append(
            {
                "type": "button",
                "style": "primary",
                "height": "sm",
                "color": "#156B6C",
                "action": postback_action,
            }
        )
    if detail_url:
        contents.append(
            {
                "type": "button",
                "style": "link",
                "height": "sm",
                "action": {
                    "type": "uri",
                    "label": "旅次詳情",
                    "uri": detail_url,
                },
            }
        )
    if not contents:
        contents.append(
            {
                "type": "text",
                "text": "請開啟旅次詳情查看完整資訊。",
                "size": "sm",
                "color": "#5F6B73",
                "wrap": True,
            }
        )
    return contents


def _flex_status_color(lodging: TripDisplayLodging) -> str:
    if lodging.availability_key == "available":
        return "#156B6C"
    if lodging.availability_key == "sold_out":
        return "#8C2F39"
    return "#9F5B00"


def _flex_decision_color(lodging: TripDisplayLodging) -> str:
    if lodging.decision_status == "booked":
        return "#156B6C"
    if lodging.decision_status == "dismissed":
        return "#9F5B00"
    return "#5F6B73"


def _build_decision_postback_action(
    lodging: TripDisplayLodging,
) -> dict[str, str] | None:
    if lodging.decision_status == "dismissed":
        return None
    target_status = "candidate" if lodging.decision_status == "booked" else "booked"
    label = "改回候選" if target_status == "candidate" else "已訂這間"
    return {
        "type": "postback",
        "label": label,
        "data": build_lodging_decision_postback_data(
            document_id=lodging.document_id,
            decision_status=target_status,
        ),
        "displayText": label,
    }


def build_lodging_decision_postback_data(
    *,
    document_id: str,
    decision_status: str,
) -> str:
    return urlencode(
        {
            "action": "lodging_decision",
            "document_id": document_id,
            "decision_status": decision_status,
        }
    )


def _build_platform_options(surface: TripDisplaySurface) -> str:
    options = ['<option value="">全部平台</option>']
    selected_platform = (surface.filters.platform or "").lower()
    for platform in surface.platform_options:
        selected_attr = " selected" if selected_platform == platform.lower() else ""
        options.append(
            f'<option value="{escape(platform, quote=True)}"{selected_attr}>'
            f"{escape(platform_label(platform))}</option>"
        )
    return "\n".join(options)


def _build_availability_options(filters: TripDisplayFilters) -> str:
    return "\n".join(
        (
            f'<option value="{escape(key, quote=True)}"'
            f'{" selected" if filters.availability == key else ""}>'
            f"{escape(label)}</option>"
        )
        for key, label in AVAILABILITY_LABELS.items()
    )


def _build_decision_status_options(filters: TripDisplayFilters) -> str:
    return "\n".join(
        (
            f'<option value="{escape(key, quote=True)}"'
            f'{" selected" if filters.decision_status == key else ""}>'
            f"{escape(label)}</option>"
        )
        for key, label in DECISION_STATUS_LABELS.items()
    )


def _build_sort_options(filters: TripDisplayFilters) -> str:
    return "\n".join(
        (
            f'<option value="{escape(key, quote=True)}"'
            f'{" selected" if filters.sort == key else ""}>'
            f"{escape(label)}</option>"
        )
        for key, label in SORT_LABELS.items()
    )


def _build_lodging_cards(
    lodgings: tuple[TripDisplayLodging, ...],
    *,
    request_path: str,
) -> list[str]:
    cards: list[str] = []
    for lodging in lodgings:
        chips = [
            f'<span class="chip">{escape(platform_label(lodging.platform))}</span>',
            _build_decision_chip(lodging),
            _build_availability_chip(lodging),
            f'<span class="chip">{escape(lodging.price_label)}</span>',
        ]
        meta_lines = []
        if lodging.formatted_address:
            meta_lines.append(escape(lodging.formatted_address))
        if lodging.captured_at is not None:
            meta_lines.append(
                f"收錄時間：{escape(lodging.captured_at.strftime('%Y-%m-%d %H:%M'))}"
            )
        links = [
            _build_anchor("原始連結", lodging.target_url),
        ]
        if lodging.maps_url:
            links.append(_build_anchor("地圖", lodging.maps_url))
        if lodging.notion_page_url:
            links.append(_build_anchor("Notion 頁面", lodging.notion_page_url))
        decision_actions = _build_decision_action_forms(
            lodging,
            request_path=request_path,
        )
        cards.append(
            "\n".join(
                [
                    '<article class="card">',
                    _build_lodging_thumbnail(lodging),
                    '  <div class="card-content">',
                    '    <div class="card-header">',
                    f'      <h2 class="card-title">{escape(lodging.display_name)}</h2>',
                    "    </div>",
                    f'    <div class="chip-row">{"".join(chips)}</div>',
                    (
                        f'    <p class="meta">{"<br />".join(meta_lines)}</p>'
                        if meta_lines
                        else ""
                    ),
                    f'    <div class="links">{"".join(link for link in links if link)}</div>',
                    f'    <div class="decision-actions">{decision_actions}</div>',
                    "  </div>",
                    "</article>",
                ]
            )
        )
    return cards


def _build_lodging_thumbnail(lodging: TripDisplayLodging) -> str:
    thumbnail_url = _select_lodging_thumbnail_url(lodging)
    if thumbnail_url:
        image = (
            f'<img class="card-thumbnail" src="{escape(thumbnail_url, quote=True)}"'
            f' alt="{escape(lodging.display_name, quote=True)} 縮圖" loading="lazy" />'
        )
        if lodging.target_url:
            return (
                '  <div class="card-media">'
                f'<a class="card-media-link" href="{escape(lodging.target_url, quote=True)}"'
                ' target="_blank" rel="noreferrer">'
                f"{image}</a></div>"
            )
        return f'  <div class="card-media">{image}</div>'

    return (
        '  <div class="card-media">'
        '    <div class="card-thumbnail-fallback">'
        f'      <span class="card-fallback-platform">{escape(platform_label(lodging.platform))}</span>'
        '      <span class="card-fallback-text">沒有縮圖</span>'
        "    </div>"
        "  </div>"
    )


def _select_lodging_thumbnail_url(lodging: TripDisplayLodging) -> str | None:
    return lodging.hero_image_url or lodging.line_hero_image_url


def _build_decision_chip(lodging: TripDisplayLodging) -> str:
    chip_class = "chip"
    if lodging.decision_status == "booked":
        chip_class = "chip"
    elif lodging.decision_status == "dismissed":
        chip_class = "chip warn"
    return f'<span class="{chip_class}">{escape(lodging.decision_status_label)}</span>'


def _build_availability_chip(lodging: TripDisplayLodging) -> str:
    chip_class = "chip"
    if lodging.availability_key == "sold_out":
        chip_class = "chip danger"
    elif lodging.availability_key == "unknown":
        chip_class = "chip warn"
    return f'<span class="{chip_class}">{escape(lodging.availability_label)}</span>'


def _build_decision_action_forms(
    lodging: TripDisplayLodging,
    *,
    request_path: str,
) -> str:
    action_path = (
        f"{escape(request_path, quote=True)}/lodgings/"
        f"{escape(lodging.document_id, quote=True)}/decision"
    )
    if lodging.decision_status == "booked":
        return _build_decision_form(
            action_path=action_path,
            decision_status="candidate",
            label="改回候選",
            button_class="secondary",
        )
    if lodging.decision_status == "dismissed":
        return _build_decision_form(
            action_path=action_path,
            decision_status="candidate",
            label="改回候選",
            button_class="secondary",
        )
    return "".join(
        [
            _build_decision_form(
                action_path=action_path,
                decision_status="booked",
                label="已訂這間",
            ),
            _build_decision_form(
                action_path=action_path,
                decision_status="dismissed",
                label="不考慮這間",
                button_class="secondary",
            ),
        ]
    )


def _build_decision_form(
    *,
    action_path: str,
    decision_status: str,
    label: str,
    button_class: str | None = None,
) -> str:
    class_attr = f' class="{escape(button_class, quote=True)}"' if button_class else ""
    return (
        f'<form method="post" action="{action_path}">'
        f'<input type="hidden" name="decision_status" value="{escape(decision_status, quote=True)}" />'
        f'<button type="submit"{class_attr}>{escape(label)}</button>'
        "</form>"
    )


def _build_anchor(label: str, url: str | None) -> str:
    if not url:
        return ""
    return (
        f'<a href="{escape(url, quote=True)}" target="_blank" rel="noreferrer">'
        f"{escape(label)}</a>"
    )


def _build_empty_state() -> str:
    return (
        '<div class="empty">'
        "這個旅次還沒有候選住宿。回到 LINE 貼住宿連結後，這裡會直接顯示 Mongo 裡的 canonical data。"
        "</div>"
    )
