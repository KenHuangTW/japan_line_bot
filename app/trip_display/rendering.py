from __future__ import annotations

from typing import Any
from html import escape

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


def build_line_trip_preview(
    surface: TripDisplaySurface,
    *,
    detail_url: str,
    preview_limit: int = 3,
) -> str:
    lines = [
        f"目前旅次：{surface.trip_title}",
        (
            f"候選住宿 {surface.total_lodgings} 筆"
            f"（可訂 {surface.available_count} / 已售完 {surface.sold_out_count} / 待確認 {surface.unknown_count}）"
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
                        f"{lodging.price_label}｜{lodging.availability_label}"
                    ),
                ]
            )
    else:
        lines.append("目前還沒有候選住宿，先貼 Booking / Agoda / Airbnb 連結進來。")

    if surface.visible_count > preview_limit:
        lines.append(f"還有 {surface.visible_count - preview_limit} 筆，請到旅次頁查看完整清單。")

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
        f"{surface.trip_title}：{surface.total_lodgings} 筆候選住宿，"
        f"可訂 {surface.available_count} 筆，"
        "請開啟旅次詳情查看完整清單。"
    )


def build_trip_detail_html(
    surface: TripDisplaySurface,
    *,
    request_path: str,
) -> str:
    cards = "\n".join(_build_lodging_cards(surface.lodgings)) or _build_empty_state()
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
        padding: 18px;
        border-radius: 22px;
        border: 1px solid var(--line);
        background: var(--card);
        box-shadow: 0 18px 42px rgba(48, 32, 18, 0.05);
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
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": _build_bubble_footer_contents(
                source_url=source_url,
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
    source_url: str | None,
    detail_url: str | None,
) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    if source_url:
        contents.append(
            {
                "type": "button",
                "style": "primary",
                "height": "sm",
                "color": "#156B6C",
                "action": {
                    "type": "uri",
                    "label": "開啟房源",
                    "uri": source_url,
                },
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


def _build_sort_options(filters: TripDisplayFilters) -> str:
    return "\n".join(
        (
            f'<option value="{escape(key, quote=True)}"'
            f'{" selected" if filters.sort == key else ""}>'
            f"{escape(label)}</option>"
        )
        for key, label in SORT_LABELS.items()
    )


def _build_lodging_cards(lodgings: tuple[TripDisplayLodging, ...]) -> list[str]:
    cards: list[str] = []
    for lodging in lodgings:
        chips = [
            f'<span class="chip">{escape(platform_label(lodging.platform))}</span>',
            _build_availability_chip(lodging),
            f'<span class="chip">{escape(lodging.price_label)}</span>',
        ]
        meta_lines = []
        if lodging.formatted_address:
            meta_lines.append(escape(lodging.formatted_address))
        if lodging.captured_at is not None:
            meta_lines.append(f"收錄時間：{escape(lodging.captured_at.strftime('%Y-%m-%d %H:%M'))}")
        links = [
            _build_anchor("原始連結", lodging.target_url),
        ]
        if lodging.maps_url:
            links.append(_build_anchor("地圖", lodging.maps_url))
        if lodging.notion_page_url:
            links.append(_build_anchor("Notion 頁面", lodging.notion_page_url))
        cards.append(
            "\n".join(
                [
                    '<article class="card">',
                    '  <div class="card-header">',
                    f'    <h2 class="card-title">{escape(lodging.display_name)}</h2>',
                    "  </div>",
                    f'  <div class="chip-row">{"".join(chips)}</div>',
                    (
                        f'  <p class="meta">{"<br />".join(meta_lines)}</p>'
                        if meta_lines
                        else ""
                    ),
                    f'  <div class="links">{"".join(link for link in links if link)}</div>',
                    "</article>",
                ]
            )
        )
    return cards


def _build_availability_chip(lodging: TripDisplayLodging) -> str:
    chip_class = "chip"
    if lodging.availability_key == "sold_out":
        chip_class = "chip danger"
    elif lodging.availability_key == "unknown":
        chip_class = "chip warn"
    return f'<span class="{chip_class}">{escape(lodging.availability_label)}</span>'


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
