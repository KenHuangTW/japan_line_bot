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

_UNSET = object()


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
    lodging_rows = (
        "\n".join(_build_lodging_rows(surface.lodgings, request_path=request_path))
        or _build_empty_state()
    )
    notion_action = (
        (
            '<a class="document-link"'
            f' href="{escape(surface.notion_export_url, quote=True)}"'
            ' target="_blank" rel="noreferrer">開啟 Notion 匯出</a>'
        )
        if surface.notion_export_url
        else ""
    )
    header_actions = (
        f'<div class="document-actions">{notion_action}</div>' if notion_action else ""
    )
    platform_links = _build_platform_filter_links(surface, request_path=request_path)
    quick_filter_links = _build_quick_filter_links(
        surface.filters,
        request_path=request_path,
    )
    hidden_platform_input = (
        '<input type="hidden" name="platform"'
        f' value="{escape(surface.filters.platform, quote=True)}" />'
        if surface.filters.platform
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
        --page: #f2f0ec;
        --paper: #fafaf8;
        --paper-soft: #f5f4f0;
        --ink: #1a1a1a;
        --muted: #76736b;
        --faint: #aaa59a;
        --line: #e2dfd7;
        --line-strong: #d4d0c7;
        --warning-bg: #f8ecd1;
        --warning-ink: #8a4b0f;
        --danger-bg: #f1dedc;
        --danger-ink: #8c2f39;
      }}
      * {{ box-sizing: border-box; }}
      html, body {{
        height: 100%;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        background: #ece9e3;
        font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "PingFang TC", "Noto Sans TC", sans-serif;
        color: var(--ink);
      }}
      button, select, a {{
        font: inherit;
      }}
      .trip-app {{
        display: flex;
        min-height: 100vh;
        overflow: hidden;
      }}
      .trip-sidebar {{
        width: 240px;
        flex-shrink: 0;
        display: flex;
        flex-direction: column;
        background: #fafaf8;
        border-right: 1px solid #e0ddd6;
      }}
      .sidebar-brand {{
        padding: 32px 28px 24px;
        border-bottom: 1px solid #e8e5de;
      }}
      .sidebar-eyebrow {{
        margin: 0 0 10px;
        color: var(--faint);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.58rem;
        letter-spacing: 0.32em;
        text-transform: uppercase;
      }}
      .sidebar-title {{
        margin: 0;
        font-family: "Iowan Old Style", "Hiragino Mincho ProN", "Yu Mincho", "Times New Roman", serif;
        font-size: 1.4rem;
        font-weight: 700;
        line-height: 1.3;
      }}
      .sidebar-stats {{
        padding: 4px 28px 16px;
        border-bottom: 1px solid #e8e5de;
      }}
      .stats-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        margin-top: 16px;
        border-top: 1px solid var(--line);
        border-left: 1px solid var(--line);
      }}
      .stat-cell {{
        min-width: 0;
        padding: 12px 0;
        text-align: center;
        border-right: 1px solid var(--line);
        border-bottom: 1px solid var(--line);
      }}
      .stat-value {{
        display: block;
        color: var(--ink);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 1.6rem;
        font-weight: 600;
        line-height: 1.1;
      }}
      .stat-label {{
        display: block;
        margin-top: 5px;
        color: var(--muted);
        font-size: 0.62rem;
        line-height: 1.3;
        letter-spacing: 0.08em;
      }}
      .sidebar-sections {{
        flex: 1;
        padding: 20px 28px;
        overflow: auto;
      }}
      .sidebar-section + .sidebar-section {{
        margin-top: 24px;
      }}
      .section-label {{
        margin: 0 0 12px;
        color: var(--faint);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.58rem;
        letter-spacing: 0.24em;
        text-transform: uppercase;
      }}
      .sidebar-filter-list {{
        display: flex;
        flex-direction: column;
        gap: 2px;
      }}
      .sidebar-filter-link {{
        display: block;
        padding: 8px 12px;
        color: #666;
        font-size: 0.82rem;
        text-decoration: none;
      }}
      .sidebar-filter-link.is-active {{
        background: #1a1a1a;
        color: white;
      }}
      .sidebar-footer {{
        padding: 16px 28px;
        border-top: 1px solid #e8e5de;
        color: #ccc;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.62rem;
      }}
      .trip-main {{
        flex: 1;
        display: flex;
        flex-direction: column;
        min-width: 0;
        background: #f5f3ef;
        overflow: hidden;
      }}
      .trip-toolbar {{
        position: sticky;
        top: 0;
        z-index: 10;
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 18px 36px;
        background: var(--paper);
        border-bottom: 1px solid #e8e5de;
      }}
      .toolbar-count {{
        color: var(--faint);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.74rem;
      }}
      .trip-controls {{
        margin-left: auto;
        display: grid;
        grid-auto-flow: column;
        gap: 8px;
        align-items: center;
      }}
      .toolbar-control {{
        display: flex;
        align-items: center;
        gap: 8px;
        color: #888;
        font-size: 0.76rem;
      }}
      select {{
        min-height: 34px;
        padding: 4px 8px;
        border: 1px solid #e0ddd6;
        border-radius: 0;
        background: #fff;
        color: #555;
        font-size: 0.76rem;
      }}
      .apply-button, .reset-link, .decision-button {{
        display: inline-flex;
        justify-content: center;
        align-items: center;
        min-height: 32px;
        padding: 0 14px;
        border-radius: 0;
        text-decoration: none;
        cursor: pointer;
        font-size: 0.8rem;
      }}
      .apply-button {{
        border: 1px solid var(--ink);
        background: var(--ink);
        color: white;
      }}
      .document-actions {{
        display: flex;
        align-items: center;
        gap: 8px;
      }}
      .document-link {{
        display: inline-flex;
        align-items: center;
        min-height: 32px;
        padding: 0 10px;
        border: 1px solid #e0ddd6;
        background: white;
        color: var(--muted);
        font-size: 0.72rem;
        text-decoration: none;
      }}
      .reset-link {{
        border: 1px solid var(--line-strong);
        color: var(--ink);
        background: #fff;
      }}
      .lodging-list {{
        padding: 24px 36px;
        overflow: auto;
      }}
      .lodging-row {{
        padding: 20px 0;
        border-bottom: 1px solid var(--line);
        background: #fafaf8;
      }}
      .lodging-row:nth-child(even) {{
        background: #f7f5f1;
      }}
      .lodging-row.is-dismissed {{
        opacity: 0.35;
      }}
      .lodging-row-shell {{
        display: grid;
        grid-template-columns: 24px 160px minmax(0, 1fr);
        gap: 20px;
        align-items: start;
        padding: 0 4px;
      }}
      .lodging-index {{
        width: 24px;
        padding-top: 3px;
        color: #ccc;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.68rem;
      }}
      .lodging-thumbnail-frame {{
        width: 160px;
        height: 110px;
        overflow: hidden;
        outline: 1px solid #ddd9d0;
        background: #e8e6e0;
      }}
      .lodging-thumbnail-link {{
        display: block;
        width: 100%;
        height: 100%;
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
        display: flex;
        width: 100%;
        height: 100%;
        flex-direction: column;
        justify-content: center;
        gap: 6px;
        padding: 12px;
        background: #e8e6e0;
        color: var(--muted);
        text-align: center;
      }}
      .fallback-platform {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.62rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .fallback-text {{
        font-size: 0.68rem;
      }}
      .lodging-content {{
        min-width: 0;
      }}
      .lodging-tags {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        align-items: center;
        margin-bottom: 10px;
      }}
      .lodging-tag {{
        padding: 2px 8px;
        font-size: 0.62rem;
        line-height: 1.4;
      }}
      .lodging-tag.platform {{
        background: #f0ede6;
        color: #888;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        letter-spacing: 0.05em;
      }}
      .lodging-tag.booked {{
        background: #1a1a1a;
        color: white;
        letter-spacing: 0.08em;
      }}
      .lodging-tag.pending {{
        background: var(--warning-bg);
        color: var(--warning-ink);
      }}
      .lodging-tag.dismissed {{
        background: var(--danger-bg);
        color: var(--danger-ink);
      }}
      .lodging-title {{
        margin: 0;
        color: var(--ink);
        font-size: 0.92rem;
        font-weight: 500;
        line-height: 1.65;
        overflow-wrap: anywhere;
      }}
      .lodging-facts, .lodging-meta, .lodging-links, .decision-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }}
      .lodging-facts {{
        margin-top: 8px;
        color: var(--muted);
        font-size: 0.72rem;
      }}
      .fact.is-warning {{
        color: var(--warning-ink);
      }}
      .fact.is-danger {{
        color: var(--danger-ink);
      }}
      .lodging-meta {{
        margin-top: 10px;
        color: #bbb;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.68rem;
      }}
      .meta-item {{
        min-width: 0;
      }}
      .meta-item + .meta-item::before {{
        content: "·";
        margin-right: 8px;
        color: var(--line-strong);
      }}
      .lodging-links {{
        margin-left: auto;
        gap: 12px;
        font-size: 0.72rem;
      }}
      .lodging-links a {{
        color: #bbb;
        text-decoration: none;
        border-bottom: 1px solid #ddd9d0;
      }}
      .lodging-actions {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 14px;
        flex-wrap: wrap;
      }}
      .decision-form {{
        margin: 0;
        padding: 0;
        border: 0;
        background: transparent;
      }}
      .decision-button {{
        border: 1px solid var(--ink);
        background: var(--ink);
        color: white;
      }}
      .decision-button.secondary {{
        border: 1px solid var(--line-strong);
        background: #fff;
        color: #999;
      }}
      .empty {{
        padding: 36px 4px;
        border-bottom: 1px solid var(--line);
        color: var(--muted);
        font-size: 0.86rem;
        line-height: 1.7;
      }}
      @media (max-width: 980px) {{
        .trip-app {{
          display: block;
          overflow: visible;
        }}
        .trip-sidebar {{
          width: auto;
          border-right: 0;
          border-bottom: 1px solid #e8e5de;
        }}
        .sidebar-sections {{
          padding-bottom: 24px;
        }}
        .trip-main {{
          overflow: visible;
        }}
        .trip-toolbar {{
          padding: 16px 20px;
          flex-wrap: wrap;
        }}
        .trip-controls {{
          width: 100%;
          margin-left: 0;
          grid-auto-flow: row;
          justify-content: start;
        }}
        .toolbar-control {{
          width: 100%;
          justify-content: space-between;
        }}
        .document-actions {{
          width: 100%;
        }}
        .lodging-list {{
          padding: 20px;
          overflow: visible;
        }}
        .lodging-row-shell {{
          grid-template-columns: 24px 124px minmax(0, 1fr);
          gap: 16px;
        }}
        .lodging-thumbnail-frame {{
          width: 124px;
          height: 96px;
        }}
      }}
      @media (max-width: 640px) {{
        .sidebar-brand {{
          padding: 24px 20px 20px;
        }}
        .sidebar-stats,
        .sidebar-sections,
        .sidebar-footer,
        .trip-toolbar,
        .lodging-list {{
          padding-left: 18px;
          padding-right: 18px;
        }}
        .sidebar-title {{
          font-size: 1.2rem;
        }}
        .stats-grid {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .sidebar-filter-list {{
          flex-direction: row;
          flex-wrap: wrap;
        }}
        .sidebar-filter-link {{
          border: 1px solid #e0ddd6;
          background: white;
        }}
        .lodging-row-shell {{
          grid-template-columns: 20px 96px minmax(0, 1fr);
          gap: 12px;
          padding: 0;
        }}
        .lodging-thumbnail-frame {{
          width: 96px;
          height: 78px;
        }}
        .lodging-title {{
          font-size: 0.84rem;
        }}
        .lodging-actions {{
          align-items: flex-start;
        }}
        .lodging-links {{
          width: 100%;
          margin-left: 0;
        }}
      }}
      @media (max-width: 420px) {{
        .trip-toolbar {{
          padding-top: 14px;
          padding-bottom: 14px;
        }}
        .lodging-row-shell {{
          grid-template-columns: 18px 88px minmax(0, 1fr);
          gap: 10px;
        }}
        .lodging-thumbnail-frame {{
          width: 88px;
          height: 72px;
        }}
        .decision-button, .apply-button, .reset-link {{
          width: 100%;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="trip-app">
      <aside class="trip-sidebar">
        <section class="sidebar-brand">
          <p class="sidebar-eyebrow">Trip Log</p>
          <h1 class="sidebar-title">{escape(surface.trip_title)}</h1>
        </section>
        <section class="sidebar-stats" aria-label="旅次統計">
          <div class="stats-grid">
            <div class="stat-cell"><span class="stat-value">{surface.booked_count}</span><span class="stat-label">已訂</span></div>
            <div class="stat-cell"><span class="stat-value">{surface.candidate_count}</span><span class="stat-label">候選</span></div>
            <div class="stat-cell"><span class="stat-value">{surface.dismissed_count}</span><span class="stat-label">不考慮</span></div>
            <div class="stat-cell"><span class="stat-value">{surface.available_count}</span><span class="stat-label">可訂</span></div>
            <div class="stat-cell"><span class="stat-value">{surface.sold_out_count}</span><span class="stat-label">已售完</span></div>
            <div class="stat-cell"><span class="stat-value">{surface.unknown_count}</span><span class="stat-label">待確認</span></div>
          </div>
        </section>
        <section class="sidebar-sections">
          <div class="sidebar-section">
            <p class="section-label">平台篩選</p>
            <div class="sidebar-filter-list">
              {platform_links}
            </div>
          </div>
          <div class="sidebar-section">
            <p class="section-label">快速篩選</p>
            <div class="sidebar-filter-list">
              {quick_filter_links}
            </div>
          </div>
        </section>
        <footer class="sidebar-footer">LINE Japan Bot</footer>
      </aside>
      <section class="trip-main">
        <header class="trip-toolbar">
          <span class="toolbar-count">顯示 {surface.visible_count} / {surface.total_lodgings} 筆</span>
          <form class="trip-controls" method="get" action="{escape(request_path, quote=True)}">
            {hidden_platform_input}
            <label class="toolbar-control">
              <span>狀態</span>
              <select name="availability">
                {_build_availability_options(surface.filters)}
              </select>
            </label>
            <label class="toolbar-control">
              <span>決策</span>
              <select name="decision_status">
                {_build_decision_status_options(surface.filters)}
              </select>
            </label>
            <label class="toolbar-control">
              <span>排序</span>
              <select name="sort">
                {_build_sort_options(surface.filters)}
              </select>
            </label>
            <button class="apply-button" type="submit">套用</button>
            <a class="reset-link" href="{escape(request_path, quote=True)}">重設</a>
          </form>
          {header_actions}
        </header>
        <section class="lodging-list" aria-label="住宿清單">
          {lodging_rows}
        </section>
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


def _build_platform_filter_links(
    surface: TripDisplaySurface,
    *,
    request_path: str,
) -> str:
    links = [
        _build_sidebar_filter_link(
            label="全部",
            href=_build_trip_filter_href(
                request_path,
                surface.filters,
                platform=None,
            ),
            is_active=surface.filters.platform is None,
        )
    ]
    selected_platform = (surface.filters.platform or "").lower()
    for platform in surface.platform_options:
        links.append(
            _build_sidebar_filter_link(
                label=platform_label(platform),
                href=_build_trip_filter_href(
                    request_path,
                    surface.filters,
                    platform=platform,
                ),
                is_active=selected_platform == platform.lower(),
            )
        )
    return "".join(links)


def _build_quick_filter_links(
    filters: TripDisplayFilters,
    *,
    request_path: str,
) -> str:
    return "".join(
        [
            _build_sidebar_filter_link(
                label="全部",
                href=_build_trip_filter_href(
                    request_path,
                    filters,
                    availability="all",
                    decision_status="active",
                ),
                is_active=(
                    filters.availability == "all"
                    and filters.decision_status == "active"
                ),
            ),
            _build_sidebar_filter_link(
                label="已訂",
                href=_build_trip_filter_href(
                    request_path,
                    filters,
                    availability="all",
                    decision_status="booked",
                ),
                is_active=filters.decision_status == "booked",
            ),
            _build_sidebar_filter_link(
                label="待確認",
                href=_build_trip_filter_href(
                    request_path,
                    filters,
                    availability="unknown",
                    decision_status="active",
                ),
                is_active=(
                    filters.availability == "unknown"
                    and filters.decision_status == "active"
                ),
            ),
            _build_sidebar_filter_link(
                label="不考慮",
                href=_build_trip_filter_href(
                    request_path,
                    filters,
                    availability="all",
                    decision_status="dismissed",
                ),
                is_active=filters.decision_status == "dismissed",
            ),
        ]
    )


def _build_sidebar_filter_link(*, label: str, href: str, is_active: bool) -> str:
    class_name = "sidebar-filter-link"
    if is_active:
        class_name += " is-active"
    return f'<a class="{class_name}" href="{escape(href, quote=True)}">{escape(label)}</a>'


def _build_trip_filter_href(
    request_path: str,
    filters: TripDisplayFilters,
    *,
    platform: str | None | object = _UNSET,
    availability: str | object = _UNSET,
    decision_status: str | object = _UNSET,
    sort: str | object = _UNSET,
) -> str:
    query: dict[str, str] = {}
    effective_platform = filters.platform if platform is _UNSET else platform
    effective_availability = (
        filters.availability if availability is _UNSET else availability
    )
    effective_decision_status = (
        filters.decision_status if decision_status is _UNSET else decision_status
    )
    effective_sort = filters.sort if sort is _UNSET else sort

    if isinstance(effective_platform, str) and effective_platform.strip():
        query["platform"] = effective_platform
    if isinstance(effective_availability, str) and effective_availability != "all":
        query["availability"] = effective_availability
    if (
        isinstance(effective_decision_status, str)
        and effective_decision_status != "active"
    ):
        query["decision_status"] = effective_decision_status
    if isinstance(effective_sort, str) and effective_sort != "captured_desc":
        query["sort"] = effective_sort

    if not query:
        return request_path
    return f"{request_path}?{urlencode(query)}"


def _build_lodging_rows(
    lodgings: tuple[TripDisplayLodging, ...],
    *,
    request_path: str,
) -> list[str]:
    rows: list[str] = []
    total_digits = max(2, len(str(len(lodgings))))
    for index, lodging in enumerate(lodgings, start=1):
        facts = [
            f'<span class="fact">{escape(lodging.price_label)}</span>',
            _build_availability_fact(lodging),
        ]
        meta_items = []
        location_label = lodging.formatted_address or lodging.city
        if location_label:
            meta_items.append(escape(location_label))
        if lodging.captured_at is not None:
            meta_items.append(escape(lodging.captured_at.strftime("%Y-%m-%d %H:%M")))
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
        row_class = "lodging-row"
        if lodging.decision_status == "dismissed":
            row_class += " is-dismissed"
        rows.append(
            "\n".join(
                [
                    f'<article class="{row_class}">',
                    '  <div class="lodging-row-shell">',
                    f'    <div class="lodging-index">{index:0{total_digits}d}</div>',
                    _build_lodging_thumbnail(lodging),
                    '    <div class="lodging-content">',
                    f'      <div class="lodging-tags">{_build_platform_tag(lodging)}{_build_status_tag(lodging)}</div>',
                    f'      <h2 class="lodging-title">{escape(lodging.display_name)}</h2>',
                    f'      <div class="lodging-facts">{"".join(facts)}</div>',
                    (
                        f'      <div class="lodging-meta">{_join_meta_items(meta_items)}</div>'
                        if meta_items
                        else ""
                    ),
                    '      <div class="lodging-actions">',
                    f'        <div class="decision-actions">{decision_actions}</div>',
                    (
                        f'        <div class="lodging-links">{"".join(link for link in links if link)}</div>'
                        if any(links)
                        else ""
                    ),
                    "      </div>",
                    "    </div>",
                    "  </div>",
                    "</article>",
                ]
            )
        )
    return rows


def _build_lodging_thumbnail(lodging: TripDisplayLodging) -> str:
    thumbnail_url = _select_lodging_thumbnail_url(lodging)
    if thumbnail_url:
        image = (
            f'<img class="card-thumbnail" src="{escape(thumbnail_url, quote=True)}"'
            f' alt="{escape(lodging.display_name, quote=True)} 縮圖" loading="lazy" />'
        )
        if lodging.target_url:
            return (
                '    <div class="lodging-thumbnail-frame">'
                f'<a class="lodging-thumbnail-link" href="{escape(lodging.target_url, quote=True)}"'
                ' target="_blank" rel="noreferrer">'
                f"{image}</a></div>"
            )
        return f'    <div class="lodging-thumbnail-frame">{image}</div>'

    return (
        '    <div class="lodging-thumbnail-frame">'
        '    <div class="card-thumbnail-fallback">'
        f'      <span class="fallback-platform">{escape(platform_label(lodging.platform))}</span>'
        '      <span class="fallback-text">沒有縮圖</span>'
        "    </div>"
        "  </div>"
    )


def _select_lodging_thumbnail_url(lodging: TripDisplayLodging) -> str | None:
    return lodging.hero_image_url or lodging.line_hero_image_url


def _build_decision_badge(lodging: TripDisplayLodging) -> str:
    badge_class = "row-badge"
    if lodging.decision_status == "booked":
        badge_class = "row-badge"
    elif lodging.decision_status == "dismissed":
        badge_class = "row-badge is-warning"
    return f'<span class="{badge_class}">{escape(lodging.decision_status_label)}</span>'


def _build_platform_tag(lodging: TripDisplayLodging) -> str:
    return (
        '<span class="lodging-tag platform">'
        f"{escape(platform_label(lodging.platform))}"
        "</span>"
    )


def _build_status_tag(lodging: TripDisplayLodging) -> str:
    tag_class = "lodging-tag"
    if lodging.decision_status == "booked":
        tag_class += " booked"
        label = "已預訂"
    elif lodging.decision_status == "dismissed":
        tag_class += " dismissed"
        label = "不考慮"
    elif lodging.availability_key == "unknown":
        tag_class += " pending"
        label = "待確認"
    elif lodging.availability_key == "sold_out":
        tag_class += " dismissed"
        label = lodging.availability_label
    else:
        tag_class += " pending"
        label = lodging.availability_label
    return f'<span class="{tag_class}">{escape(label)}</span>'


def _build_availability_fact(lodging: TripDisplayLodging) -> str:
    fact_class = "fact"
    if lodging.availability_key == "sold_out":
        fact_class = "fact is-danger"
    elif lodging.availability_key == "unknown":
        fact_class = "fact is-warning"
    return f'<span class="{fact_class}">{escape(lodging.availability_label)}</span>'


def _join_meta_items(meta_items: list[str]) -> str:
    return "".join(f'<span class="meta-item">{item}</span>' for item in meta_items)


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
    button_classes = "decision-button"
    if button_class:
        button_classes = f"{button_classes} {button_class}"
    return (
        f'<form class="decision-form" method="post" action="{action_path}">'
        f'<input type="hidden" name="decision_status" value="{escape(decision_status, quote=True)}" />'
        f'<button class="{escape(button_classes, quote=True)}" type="submit">{escape(label)}</button>'
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
