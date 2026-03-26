from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from app.map_enrichment.models import ParsedLodgingMap

AGODA_SECONDARY_DATA_URL_PATTERN = re.compile(
    r'var\s+apiUrl="(?P<url>[^"]+)"',
    re.IGNORECASE,
)


def extract_agoda_secondary_data_url(
    html: str,
    page_url: str,
) -> str | None:
    match = AGODA_SECONDARY_DATA_URL_PATTERN.search(html)
    if match is None:
        return None

    raw_url = unescape(match.group("url")).strip()
    if not raw_url:
        return None

    return urljoin(page_url, raw_url)


def parse_agoda_secondary_data(payload: str) -> ParsedLodgingMap | None:
    try:
        document = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(document, dict):
        return None

    map_params = document.get("mapParams")
    inquiry_property = document.get("inquiryProperty")

    property_name = None
    formatted_address = None
    latitude = None
    longitude = None

    if isinstance(inquiry_property, dict):
        property_name = _normalize_string(
            inquiry_property.get("hotelNameEnglish")
            or inquiry_property.get("placeName")
        )
        formatted_address = _normalize_string(inquiry_property.get("hotelLocation"))

    if isinstance(map_params, dict):
        latlng = map_params.get("latlng")
        if (
            isinstance(latlng, list)
            and len(latlng) >= 2
            and isinstance(latlng[0], (int, float))
            and isinstance(latlng[1], (int, float))
        ):
            latitude = float(latlng[0])
            longitude = float(latlng[1])

    if (
        property_name is None
        and formatted_address is None
        and latitude is None
        and longitude is None
    ):
        return None

    map_source = (
        "agoda_secondary_data_geo"
        if latitude is not None and longitude is not None
        else "agoda_secondary_data_address"
    )
    return ParsedLodgingMap(
        property_name=property_name,
        formatted_address=formatted_address,
        latitude=latitude,
        longitude=longitude,
        map_source=map_source,
    )


def _normalize_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = " ".join(unescape(value).split())
    return normalized or None
