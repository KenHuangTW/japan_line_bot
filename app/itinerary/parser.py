from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time

from app.models import build_source_line_hash

DAY_HEADING_RE = re.compile(
    r"^##\s*第\s*(?P<day>\d+)\s*天\s*[—-]\s*"
    r"(?P<date>\d{4}-\d{2}-\d{2})"
)
TIMED_ROW_RE = re.compile(
    r"^-\s*(?P<start>\d{1,2}:\d{2})"
    r"(?:\s*[–—-]\s*(?P<end>\d{1,2}:\d{2}|（?自由）?|\(?自由\)?))?"
    r"\s*\|\s*(?P<title>[^|]+?)\s*\|\s*(?P<description>.+?)\s*$"
)


@dataclass(frozen=True)
class ParsedItineraryRow:
    source_index: int
    raw_text: str
    day_index: int | None
    date: date
    start_time: time | None
    end_time: time | None
    title: str
    description: str | None
    source_line_hash: str


@dataclass(frozen=True)
class ParsedItineraryDayNote:
    day_index: int | None
    date: date | None
    title: str
    content: str


@dataclass(frozen=True)
class ParsedItinerary:
    rows: tuple[ParsedItineraryRow, ...] = ()
    day_notes: tuple[ParsedItineraryDayNote, ...] = ()


@dataclass
class _DayContext:
    day_index: int | None = None
    date: date | None = None
    active_note_title: str | None = None
    active_note_lines: list[str] = field(default_factory=list)


def parse_itinerary_markdown(text: str) -> ParsedItinerary:
    rows: list[ParsedItineraryRow] = []
    notes: list[ParsedItineraryDayNote] = []
    context = _DayContext()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        heading_match = DAY_HEADING_RE.match(line)
        if heading_match is not None:
            _flush_note(context, notes)
            context.day_index = int(heading_match.group("day"))
            context.date = date.fromisoformat(heading_match.group("date"))
            continue

        if line.endswith("購物重點") or line in {"今日筆記", "今日備註"}:
            _flush_note(context, notes)
            context.active_note_title = line
            continue

        row_match = TIMED_ROW_RE.match(line)
        if row_match is not None and context.date is not None:
            _flush_note(context, notes)
            rows.append(
                ParsedItineraryRow(
                    source_index=line_number,
                    raw_text=line,
                    day_index=context.day_index,
                    date=context.date,
                    start_time=_parse_time(row_match.group("start")),
                    end_time=_parse_time(row_match.group("end")),
                    title=_clean_cell(row_match.group("title")),
                    description=_clean_cell(row_match.group("description")),
                    source_line_hash=build_source_line_hash(line),
                )
            )
            continue

        if context.active_note_title is not None and line.startswith("-"):
            context.active_note_lines.append(line.lstrip("- ").rstrip())

    _flush_note(context, notes)
    return ParsedItinerary(rows=tuple(rows), day_notes=tuple(notes))


def _flush_note(
    context: _DayContext,
    notes: list[ParsedItineraryDayNote],
) -> None:
    if context.active_note_title and context.active_note_lines:
        notes.append(
            ParsedItineraryDayNote(
                day_index=context.day_index,
                date=context.date,
                title=context.active_note_title,
                content="\n".join(context.active_note_lines),
            )
        )
    context.active_note_title = None
    context.active_note_lines = []


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    normalized = value.strip()
    if "自由" in normalized:
        return None
    try:
        hour, minute = normalized.split(":", maxsplit=1)
        return time(hour=int(hour), minute=int(minute))
    except ValueError:
        return None


def _clean_cell(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.replace("  ", " ").strip().split())
