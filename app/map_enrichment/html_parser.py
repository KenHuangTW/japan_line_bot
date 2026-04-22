from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

from app.lodging_links.airbnb import is_airbnb_hostname
from app.map_enrichment.models import ParsedLodgingMap

JSON_LD_SCRIPT_PATTERN = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_PATTERN = re.compile(
    r"<title[^>]*>(?P<title>.*?)</title>",
    re.IGNORECASE | re.DOTALL,
)
META_TAG_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
META_ATTR_PATTERN = re.compile(
    r'(?P<name>[a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?P<quote>"|\')(?P<value>.*?)(?P=quote)',
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_STYLE_PATTERN = re.compile(
    r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
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
SOLD_OUT_PATTERNS = (
    re.compile(r"\bsold[\s-]*out\b", re.IGNORECASE),
    re.compile(r"\bno rooms? available\b", re.IGNORECASE),
    re.compile(r"已售完"),
    re.compile(r"已無空房"),
    re.compile(r"無空房"),
    re.compile(r"查無空房"),
)


def parse_lodging_map(html: str) -> ParsedLodgingMap | None:
    html_sold_out = _extract_html_sold_out_signal(html)
    structured_candidate = _extract_best_structured_data_candidate(html)
    if structured_candidate is not None:
        return _merge_html_sold_out_signal(structured_candidate, html_sold_out)

    booking_header_candidate = _extract_booking_header_candidate(html)
    if booking_header_candidate is not None:
        return _merge_html_sold_out_signal(booking_header_candidate, html_sold_out)

    coordinates = _extract_coordinate_pair(html)
    title = _extract_title(html)
    if coordinates is not None:
        return ParsedLodgingMap(
            property_name=title,
            latitude=coordinates[0],
            longitude=coordinates[1],
            map_source="html_regex_geo",
            is_sold_out=html_sold_out[0],
            availability_source=html_sold_out[1],
        )

    if html_sold_out[0] is True:
        return ParsedLodgingMap(
            property_name=title,
            is_sold_out=True,
            availability_source=html_sold_out[1],
        )

    return None


def parse_lodging_map_from_url(
    url: str,
    *,
    map_source: str = "url_slug_fallback",
    html: str | None = None,
) -> ParsedLodgingMap | None:
    parsed_url = urlsplit(url)
    hostname = (parsed_url.hostname or "").lower()
    path = parsed_url.path.strip("/")
    if not path:
        return None

    property_slug = _extract_property_slug_from_path(hostname, path)
    property_name = _humanize_slug(property_slug) if property_slug is not None else None
    if property_name is None and is_airbnb_hostname(hostname) and html:
        property_name = _extract_title(html)
    if property_name is None:
        return None

    return ParsedLodgingMap(
        property_name=property_name,
        map_source=map_source,
    )


def extract_lodging_hero_image_url(
    html: str,
    *,
    base_url: str | None = None,
) -> str | None:
    meta_image_url = _extract_meta_image_url(html)
    if meta_image_url is not None:
        return _normalize_image_url(meta_image_url, base_url=base_url)

    structured_image_url = _extract_structured_data_image_url(html)
    if structured_image_url is not None:
        return _normalize_image_url(structured_image_url, base_url=base_url)

    return None


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
    address_details = _decompose_delimited_address(formatted_address)

    return ParsedLodgingMap(
        property_name=_extract_title(html),
        formatted_address=formatted_address,
        street_address=address_details["street_address"],
        district=address_details["district"],
        city=address_details["city"],
        region=address_details["region"],
        postal_code=address_details["postal_code"],
        country_name=address_details["country_name"],
        country_code=address_details["country_code"],
        map_source="booking_header_address",
    )


def _extract_html_sold_out_signal(html: str) -> tuple[bool | None, str | None]:
    visible_text = _extract_visible_text(html)
    if visible_text is None:
        return None, None

    if any(pattern.search(visible_text) for pattern in SOLD_OUT_PATTERNS):
        return True, "html_visible_text_sold_out"

    return None, None


def _merge_html_sold_out_signal(
    candidate: ParsedLodgingMap,
    html_sold_out: tuple[bool | None, str | None],
) -> ParsedLodgingMap:
    if candidate.is_sold_out is not None:
        return candidate
    if html_sold_out[0] is not True:
        return candidate

    return ParsedLodgingMap(
        property_name=candidate.property_name,
        hero_image_url=candidate.hero_image_url,
        formatted_address=candidate.formatted_address,
        street_address=candidate.street_address,
        district=candidate.district,
        city=candidate.city,
        region=candidate.region,
        postal_code=candidate.postal_code,
        country_name=candidate.country_name,
        country_code=candidate.country_code,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        place_id=candidate.place_id,
        map_source=candidate.map_source,
        property_type=candidate.property_type,
        room_count=candidate.room_count,
        bedroom_count=candidate.bedroom_count,
        bathroom_count=candidate.bathroom_count,
        amenities=candidate.amenities,
        details_source=candidate.details_source,
        price_amount=candidate.price_amount,
        price_currency=candidate.price_currency,
        pricing_source=candidate.pricing_source,
        is_sold_out=True,
        availability_source=html_sold_out[1],
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


def _extract_visible_text(html: str) -> str | None:
    stripped = SCRIPT_STYLE_PATTERN.sub(" ", html)
    text = _strip_tags(stripped)
    if text is None:
        return None
    normalized = " ".join(text.split())
    return normalized or None


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
    hero_image_url = _extract_image_url(node.get("image"))
    address_details = _extract_address_details(node.get("address"))
    formatted_address = _format_address(address_details)
    latitude = _parse_float(_extract_geo_value(node, "latitude"))
    longitude = _parse_float(_extract_geo_value(node, "longitude"))
    property_type = _extract_property_type(node.get("@type"))
    room_count = _parse_int(
        node.get("numberOfRooms")
        or node.get("numberOfAccommodationUnits")
        or node.get("numberOfUnit")
    )
    bedroom_count = _parse_int(node.get("numberOfBedrooms"))
    bathroom_count = _parse_float(
        node.get("numberOfBathroomsTotal") or node.get("numberOfBathrooms")
    )
    amenities = _extract_amenities(node)
    price_amount, price_currency = _extract_offer(node)

    if latitude is None or longitude is None:
        coordinates = _extract_coordinate_pair(json.dumps(node, ensure_ascii=False))
        if coordinates is not None:
            latitude, longitude = coordinates

    if not _has_extractable_content(
        formatted_address=formatted_address,
        latitude=latitude,
        longitude=longitude,
        property_type=property_type,
        room_count=room_count,
        bedroom_count=bedroom_count,
        bathroom_count=bathroom_count,
        amenities=amenities,
        price_amount=price_amount,
        price_currency=price_currency,
    ):
        return None

    map_source = None
    if latitude is not None and longitude is not None:
        map_source = "structured_data_geo"
    elif formatted_address:
        map_source = "structured_data_address"

    details_source = "structured_data_details" if _has_detail_content(
        property_type=property_type,
        room_count=room_count,
        bedroom_count=bedroom_count,
        bathroom_count=bathroom_count,
        amenities=amenities,
    ) else None
    pricing_source = (
        "structured_data_offer"
        if price_amount is not None or price_currency is not None
        else None
    )

    return ParsedLodgingMap(
        property_name=property_name,
        hero_image_url=hero_image_url,
        formatted_address=formatted_address,
        street_address=address_details["street_address"],
        district=address_details["district"],
        city=address_details["city"],
        region=address_details["region"],
        postal_code=address_details["postal_code"],
        country_name=address_details["country_name"],
        country_code=address_details["country_code"],
        latitude=latitude,
        longitude=longitude,
        place_id=_normalize_string(node.get("place_id")),
        map_source=map_source,
        property_type=property_type,
        room_count=room_count,
        bedroom_count=bedroom_count,
        bathroom_count=bathroom_count,
        amenities=amenities,
        details_source=details_source,
        price_amount=price_amount,
        price_currency=price_currency,
        pricing_source=pricing_source,
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
    if candidate.has_details:
        score += 2
    if candidate.has_pricing:
        score += 1
    return score


def _is_lodging_type(raw_type: Any) -> bool:
    if isinstance(raw_type, str):
        return raw_type.strip().lower() in HOTEL_TYPES
    if isinstance(raw_type, list):
        return any(_is_lodging_type(item) for item in raw_type)
    return False


def _extract_address_details(value: Any) -> dict[str, str | None]:
    empty_details = {
        "street_address": None,
        "district": None,
        "city": None,
        "region": None,
        "postal_code": None,
        "country_name": None,
        "country_code": None,
    }
    if isinstance(value, str):
        return {
            **empty_details,
            **_decompose_delimited_address(value),
        }

    if not isinstance(value, dict):
        return empty_details

    country_name, country_code = _extract_country(value.get("addressCountry"))
    return {
        "street_address": _normalize_string(value.get("streetAddress")),
        "district": _normalize_string(
            value.get("district")
            or value.get("addressCounty")
            or value.get("subLocality")
            or value.get("addressDistrict")
        ),
        "city": _normalize_string(value.get("addressLocality")),
        "region": _normalize_string(value.get("addressRegion")),
        "postal_code": _normalize_string(value.get("postalCode")),
        "country_name": country_name,
        "country_code": country_code,
    }


def _extract_country(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        country_name = _normalize_string(
            value.get("name") or value.get("addressCountry")
        )
        country_code = _normalize_country_code(
            value.get("alpha2Code")
            or value.get("code")
            or value.get("identifier")
            or country_name
        )
        if country_name and country_code and country_name.upper() == country_code:
            country_name = None
        return country_name, country_code

    normalized = _normalize_string(value)
    if normalized is None:
        return None, None
    country_code = _normalize_country_code(normalized)
    if country_code is not None and normalized.upper() == country_code:
        return None, country_code
    return normalized, country_code


def _normalize_country_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if len(normalized) == 2 and normalized.isalpha():
        return normalized
    return None


def _format_address(details: dict[str, str | None]) -> str | None:
    parts: list[str] = []
    for key in (
        "street_address",
        "district",
        "city",
        "region",
        "postal_code",
        "country_name",
        "country_code",
    ):
        part = details.get(key)
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


def _extract_property_type(raw_type: Any) -> str | None:
    if isinstance(raw_type, str):
        normalized = raw_type.strip().lower()
        return normalized or None
    if isinstance(raw_type, list):
        for item in raw_type:
            property_type = _extract_property_type(item)
            if property_type is not None:
                return property_type
    return None


def _extract_meta_image_url(html: str) -> str | None:
    preferred_keys = (
        "og:image",
        "og:image:url",
        "twitter:image",
        "twitter:image:src",
    )
    for tag in META_TAG_PATTERN.findall(html):
        attributes = {
            match.group("name").strip().lower(): unescape(match.group("value")).strip()
            for match in META_ATTR_PATTERN.finditer(tag)
        }
        key = attributes.get("property") or attributes.get("name")
        if key is None or key.lower() not in preferred_keys:
            continue
        content = attributes.get("content")
        if content:
            return content
    return None


def _extract_structured_data_image_url(html: str) -> str | None:
    best_candidate: tuple[int, str] | None = None
    for script_body in JSON_LD_SCRIPT_PATTERN.findall(html):
        payload = _load_json(script_body)
        if payload is None:
            continue
        for node in _walk_nodes(payload):
            image_url = _extract_image_url(node.get("image"))
            if image_url is None:
                continue
            score = 0
            if _is_lodging_type(node.get("@type")):
                score += 4
            if _normalize_string(node.get("name")):
                score += 2
            if isinstance(node.get("address"), (dict, str)):
                score += 1
            if best_candidate is None or score > best_candidate[0]:
                best_candidate = (score, image_url)
    if best_candidate is None:
        return None
    return best_candidate[1]


def _extract_image_url(value: Any) -> str | None:
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, dict):
        return (
            _normalize_string(value.get("url"))
            or _normalize_string(value.get("contentUrl"))
            or _normalize_string(value.get("@id"))
        )
    if isinstance(value, list):
        for item in value:
            image_url = _extract_image_url(item)
            if image_url is not None:
                return image_url
    return None


def _normalize_image_url(value: str, *, base_url: str | None) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.startswith(("http://", "https://")):
        return normalized
    if normalized.startswith("//"):
        return f"https:{normalized}"
    if base_url is not None:
        resolved = urljoin(base_url, normalized)
        if resolved.startswith(("http://", "https://")):
            return resolved
    return None


def _extract_amenities(node: dict[str, Any]) -> tuple[str, ...]:
    amenities: list[str] = []

    amenity_feature = node.get("amenityFeature")
    if isinstance(amenity_feature, list):
        for item in amenity_feature:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if value is False:
                continue
            name = _normalize_string(item.get("name"))
            if name:
                amenities.append(name)

    raw_amenities = node.get("amenities")
    if isinstance(raw_amenities, list):
        for item in raw_amenities:
            name = _normalize_string(item)
            if name:
                amenities.append(name)

    return tuple(dict.fromkeys(amenities))


def _extract_offer(node: dict[str, Any]) -> tuple[float | None, str | None]:
    offers = node.get("offers")
    candidates = offers if isinstance(offers, list) else [offers]

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        price_amount = _parse_float(
            candidate.get("price")
            or candidate.get("lowPrice")
            or candidate.get("highPrice")
        )
        price_currency = _normalize_currency(candidate.get("priceCurrency"))
        if price_amount is None and price_currency is None:
            continue
        return price_amount, price_currency

    return None, None


def _normalize_currency(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized or None


def _has_extractable_content(
    *,
    formatted_address: str | None,
    latitude: float | None,
    longitude: float | None,
    property_type: str | None,
    room_count: int | None,
    bedroom_count: int | None,
    bathroom_count: float | None,
    amenities: tuple[str, ...],
    price_amount: float | None,
    price_currency: str | None,
) -> bool:
    return any(
        (
            formatted_address,
            latitude is not None,
            longitude is not None,
            property_type,
            room_count is not None,
            bedroom_count is not None,
            bathroom_count is not None,
            bool(amenities),
            price_amount is not None,
            price_currency,
        )
    )


def _has_detail_content(
    *,
    property_type: str | None,
    room_count: int | None,
    bedroom_count: int | None,
    bathroom_count: float | None,
    amenities: tuple[str, ...],
) -> bool:
    return any(
        (
            property_type,
            room_count is not None,
            bedroom_count is not None,
            bathroom_count is not None,
            bool(amenities),
        )
    )


def _decompose_delimited_address(value: str) -> dict[str, str | None]:
    parts = [_normalize_string(part) for part in value.split(",")]
    normalized_parts = [part for part in parts if part]
    details = {
        "street_address": None,
        "district": None,
        "city": None,
        "region": None,
        "postal_code": None,
        "country_name": None,
        "country_code": None,
    }
    if not normalized_parts:
        return details

    country_value = None
    if len(normalized_parts) >= 6:
        (
            details["street_address"],
            details["district"],
            details["city"],
            details["region"],
            details["postal_code"],
            country_value,
        ) = normalized_parts[:6]
    elif len(normalized_parts) == 5:
        (
            details["street_address"],
            details["city"],
            details["region"],
            details["postal_code"],
            country_value,
        ) = normalized_parts
    elif len(normalized_parts) == 4:
        (
            details["street_address"],
            details["city"],
            details["region"],
            country_value,
        ) = normalized_parts
    elif len(normalized_parts) >= 2:
        details["street_address"] = normalized_parts[0]
        country_value = normalized_parts[-1]
    else:
        details["street_address"] = normalized_parts[0]

    if country_value is not None:
        country_name, country_code = _extract_country(country_value)
        details["country_name"] = country_name
        details["country_code"] = country_code
    return details


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = float(normalized)
    except ValueError:
        return None
    if not parsed.is_integer():
        return None
    return int(parsed)


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

    title = re.sub(r"\s+\|\s+Booking\.com$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*(?:\||-)\s*Airbnb$", "", title, flags=re.IGNORECASE)
    return title.strip() or None


def _strip_tags(value: str) -> str | None:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return _normalize_string(without_tags)


def _normalize_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = " ".join(unescape(value).split())
    return normalized or None
