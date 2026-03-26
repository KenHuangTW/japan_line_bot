from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Iterable
from urllib.parse import urlsplit

from app.map_enrichment.models import ParsedLodgingMap

JSON_LD_SCRIPT_PATTERN = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_PATTERN = re.compile(
    r"<title[^>]*>(?P<title>.*?)</title>",
    re.IGNORECASE | re.DOTALL,
)
BOOKING_ADDRESS_PATTERNS = (
    re.compile(
        r'data-testid=["\']PropertyHeaderAddress(?:Desktop|Mobile)?["\'][^>]*>(?P<value>.*?)</',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r'class=["\'][^"\']*hp_address_subtitle[^"\']*["\'][^>]*>(?P<value>.*?)</',
        re.IGNORECASE | re.DOTALL,
    ),
)
HOTEL_TYPES = {
    "hotel",
    "lodgingbusiness",
    "resort",
    "hostel",
    "motel",
    "bedandbreakfast",
    "apartmenthotel",
    "vacationrental",
}


def parse_lodging_map(html: str) -> ParsedLodgingMap | None:
    structured_candidate = _extract_best_structured_data_candidate(html)
    if structured_candidate is not None:
        return structured_candidate

    booking_header_candidate = _extract_booking_header_candidate(html)
    if booking_header_candidate is not None:
        return booking_header_candidate

    coordinates = _extract_coordinate_pair(html)
    if coordinates is None:
        return None

    title = _extract_title(html)
    return ParsedLodgingMap(
        property_name=title,
        latitude=coordinates[0],
        longitude=coordinates[1],
        map_source="html_regex_geo",
    )


def parse_lodging_map_from_url(url: str) -> ParsedLodgingMap | None:
    parsed_url = urlsplit(url)
    hostname = (parsed_url.hostname or "").lower()
    path = parsed_url.path.strip("/")
    if not path:
        return None

    property_slug = _extract_property_slug_from_path(hostname, path)
    if property_slug is None:
        return None

    property_name = _humanize_slug(property_slug)
    if property_name is None:
        return None

    return ParsedLodgingMap(
        property_name=property_name,
        map_source="url_slug_fallback",
    )


def _extract_best_structured_data_candidate(html: str) -> ParsedLodgingMap | None:
    best_candidate: tuple[int, ParsedLodgingMap] | None = None

    for script_body in JSON_LD_SCRIPT_PATTERN.findall(html):
        payload = _load_json(script_body)
        if payload is None:
            continue

        for node in _walk_nodes(payload):
            candidate = _candidate_from_node(node)
            if candidate is None:
                continue

            score = _score_candidate(node, candidate)
            if best_candidate is None or score > best_candidate[0]:
                best_candidate = (score, candidate)

    if best_candidate is None:
        return None

    return best_candidate[1]


def _extract_booking_header_candidate(html: str) -> ParsedLodgingMap | None:
    formatted_address = _extract_booking_header_address(html)
    if formatted_address is None:
        return None

    return ParsedLodgingMap(
        property_name=_extract_title(html),
        formatted_address=formatted_address,
        map_source="booking_header_address",
    )


def _extract_booking_header_address(html: str) -> str | None:
    for pattern in BOOKING_ADDRESS_PATTERNS:
        match = pattern.search(html)
        if match is None:
            continue

        value = _strip_tags(match.group("value"))
        if value is not None:
            return value

    return None


def _extract_property_slug_from_path(hostname: str, path: str) -> str | None:
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return None

    if "booking.com" in hostname:
        filename = segments[-1]
        if not filename.endswith(".html"):
            return None
        stem = filename[:-5]
        return re.sub(r"\.[a-z]{2}(?:-[a-z]{2})?$", "", stem, flags=re.IGNORECASE)

    if "agoda.com" in hostname:
        if "hotel" in segments:
            hotel_index = segments.index("hotel")
            if hotel_index > 0:
                return segments[hotel_index - 1]
        filename = segments[-1]
        if filename.endswith(".html"):
            return filename[:-5]

    return None


def _humanize_slug(slug: str) -> str | None:
    normalized = re.sub(r"[-_]+", " ", slug).strip()
    if not normalized:
        return None

    return " ".join(part.capitalize() for part in normalized.split())


def _load_json(script_body: str) -> Any | None:
    raw_body = script_body.strip()
    if not raw_body:
        return None

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return None


def _walk_nodes(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            yield from _walk_nodes(value)
        return

    if isinstance(payload, list):
        for item in payload:
            yield from _walk_nodes(item)


def _candidate_from_node(node: dict[str, Any]) -> ParsedLodgingMap | None:
    property_name = _normalize_string(node.get("name")) or _normalize_string(
        node.get("headline")
    )
    formatted_address = _format_address(node.get("address"))
    latitude = _parse_float(_extract_geo_value(node, "latitude"))
    longitude = _parse_float(_extract_geo_value(node, "longitude"))

    if latitude is None or longitude is None:
        coordinates = _extract_coordinate_pair(json.dumps(node, ensure_ascii=False))
        if coordinates is not None:
            latitude, longitude = coordinates

    if latitude is None and longitude is None and formatted_address is None:
        return None

    map_source = "structured_data_geo" if latitude is not None and longitude is not None else "structured_data_address"

    return ParsedLodgingMap(
        property_name=property_name,
        formatted_address=formatted_address,
        latitude=latitude,
        longitude=longitude,
        place_id=_normalize_string(node.get("place_id")),
        map_source=map_source,
    )


def _score_candidate(node: dict[str, Any], candidate: ParsedLodgingMap) -> int:
    score = 0
    if _is_lodging_type(node.get("@type")):
        score += 4
    if candidate.latitude is not None and candidate.longitude is not None:
        score += 4
    if candidate.formatted_address:
        score += 3
    if candidate.property_name:
        score += 2
    return score


def _is_lodging_type(raw_type: Any) -> bool:
    if isinstance(raw_type, str):
        return raw_type.strip().lower() in HOTEL_TYPES
    if isinstance(raw_type, list):
        return any(_is_lodging_type(item) for item in raw_type)
    return False


def _format_address(value: Any) -> str | None:
    if isinstance(value, str):
        return _normalize_string(value)

    if not isinstance(value, dict):
        return None

    parts: list[str] = []
    for key in (
        "streetAddress",
        "addressLocality",
        "addressRegion",
        "postalCode",
        "addressCountry",
    ):
        part = _normalize_string(value.get(key))
        if part and part not in parts:
            parts.append(part)

    if not parts:
        return None

    return ", ".join(parts)


def _extract_geo_value(node: dict[str, Any], key: str) -> Any:
    geo = node.get("geo")
    if isinstance(geo, dict) and geo.get(key) is not None:
        return geo.get(key)
    return node.get(key)


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        return None

    try:
        return float(value.strip())
    except ValueError:
        return None


def _extract_coordinate_pair(raw_text: str) -> tuple[float, float] | None:
    latitude_match = re.search(
        r'"(?:latitude|lat)"\s*:\s*"?(?P<value>-?\d+(?:\.\d+)?)"?',
        raw_text,
        re.IGNORECASE,
    )
    longitude_match = re.search(
        r'"(?:longitude|lng|lon|long)"\s*:\s*"?(?P<value>-?\d+(?:\.\d+)?)"?',
        raw_text,
        re.IGNORECASE,
    )
    if latitude_match is None or longitude_match is None:
        return None

    return (
        float(latitude_match.group("value")),
        float(longitude_match.group("value")),
    )


def _extract_title(html: str) -> str | None:
    match = TITLE_PATTERN.search(html)
    if match is None:
        return None
    title = _normalize_string(unescape(match.group("title")))
    if title is None:
        return None

    return re.sub(r"\s+\|\s+Booking\.com$", "", title, flags=re.IGNORECASE)


def _strip_tags(value: str) -> str | None:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return _normalize_string(without_tags)


def _normalize_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = " ".join(unescape(value).split())
    return normalized or None
