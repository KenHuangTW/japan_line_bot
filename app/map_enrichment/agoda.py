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
SOLD_OUT_TEXT_PATTERN = re.compile(
    r"sold\s*out|已售完|已無空房|無空房|查無空房",
    re.IGNORECASE,
)
PLACEHOLDER_IMAGE_MARKERS = (
    "/images/default/",
    "image-place-holder",
    "preload.gif",
    "img-building",
    "logo",
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
    property_type = None
    room_count = None
    bedroom_count = None
    bathroom_count = None
    city = None
    country_name = None

    if isinstance(inquiry_property, dict):
        property_name = _first_non_empty_string(
            inquiry_property.get("placeName"),
            inquiry_property.get("hotelName"),
            inquiry_property.get("hotelNameTranslated"),
            inquiry_property.get("hotelNameLocal"),
            inquiry_property.get("hotelNameEnglish"),
        )
        formatted_address = _normalize_string(inquiry_property.get("hotelLocation"))
        property_type = _normalize_string(
            inquiry_property.get("propertyType")
            or inquiry_property.get("propertyTypeName")
            or inquiry_property.get("accommodationType")
        )
        room_count = _parse_int(
            inquiry_property.get("numberOfRooms") or inquiry_property.get("roomCount")
        )
        bedroom_count = _parse_int(
            inquiry_property.get("numberOfBedrooms")
            or inquiry_property.get("bedroomCount")
        )
        bathroom_count = _parse_float(
            inquiry_property.get("numberOfBathrooms")
            or inquiry_property.get("bathroomCount")
        )

    hero_image_url = _extract_hero_image_url(document, inquiry_property)
    city, country_name = _extract_breadcrumb_location(document.get("breadcrumbs"))

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

    amenities = _extract_amenities(document, inquiry_property)
    price_amount = _extract_price_amount(document, inquiry_property)
    price_currency = (
        _extract_price_currency(document, inquiry_property)
        if price_amount is not None
        else None
    )
    is_sold_out, availability_source = _extract_availability(document)

    if not any(
        (
            property_name,
            formatted_address,
            city,
            country_name,
            latitude is not None,
            longitude is not None,
            property_type,
            room_count is not None,
            bedroom_count is not None,
            bathroom_count is not None,
            bool(amenities),
            price_amount is not None,
            price_currency,
            is_sold_out is not None,
        )
    ):
        return None

    map_source = (
        "agoda_secondary_data_geo"
        if latitude is not None and longitude is not None
        else "agoda_secondary_data_address"
    )
    return ParsedLodgingMap(
        property_name=property_name,
        hero_image_url=hero_image_url,
        formatted_address=formatted_address,
        city=city,
        country_name=country_name,
        latitude=latitude,
        longitude=longitude,
        map_source=map_source,
        property_type=property_type,
        room_count=room_count,
        bedroom_count=bedroom_count,
        bathroom_count=bathroom_count,
        amenities=amenities,
        details_source=(
            "agoda_secondary_data_details"
            if any(
                (
                    property_type,
                    room_count is not None,
                    bedroom_count is not None,
                    bathroom_count is not None,
                    bool(amenities),
                )
            )
            else None
        ),
        price_amount=price_amount,
        price_currency=price_currency,
        pricing_source=(
            "agoda_secondary_data_pricing"
            if price_amount is not None
            else None
        ),
        is_sold_out=is_sold_out,
        availability_source=availability_source,
    )


def _extract_hero_image_url(
    document: dict[str, Any],
    inquiry_property: dict[str, Any] | Any,
) -> str | None:
    protocol = _normalize_string(document.get("protocol")) or "https:"
    candidates: list[Any] = []

    mosaic_init_data = document.get("mosaicInitData")
    if isinstance(mosaic_init_data, dict):
        candidates.extend(_extract_mosaic_image_candidates(mosaic_init_data))

    if isinstance(inquiry_property, dict):
        candidates.extend(
            [
                inquiry_property.get("hotelImage"),
                inquiry_property.get("imageUrl"),
                inquiry_property.get("imageURL"),
                inquiry_property.get("mainImageUrl"),
                inquiry_property.get("mainImageURL"),
            ]
        )

    candidates.append(
        _read_nested_string(document, "mapParams", "review", "hotelImageUrl")
    )
    candidates.extend(_extract_room_image_candidates(document.get("datelessMasterRoomInfo")))

    for candidate in candidates:
        normalized = _normalize_image_url(candidate, protocol=protocol)
        if normalized is not None:
            return normalized
    return None


def _extract_mosaic_image_candidates(mosaic_init_data: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []
    for collection_key in ("mosaicImages", "images"):
        images = mosaic_init_data.get(collection_key)
        if not isinstance(images, list):
            continue
        for image in images:
            if not isinstance(image, dict):
                continue
            candidates.extend(
                [
                    image.get("location"),
                    image.get("locationMediumRectangle"),
                    image.get("locationLarge"),
                    image.get("locationXL"),
                    image.get("locationXxl"),
                    image.get("url"),
                    image.get("imageUrl"),
                ]
            )
    return candidates


def _extract_room_image_candidates(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []

    candidates: list[Any] = []
    for room in value:
        if not isinstance(room, dict):
            continue
        images = room.get("images")
        if isinstance(images, list):
            candidates.extend(images)
    return candidates


def _normalize_image_url(value: Any, *, protocol: str) -> str | None:
    normalized = _normalize_string(value)
    if normalized is None:
        return None

    if _is_placeholder_image_url(normalized):
        return None

    if normalized.startswith("//"):
        scheme = "https:" if protocol not in {"http:", "https:"} else protocol
        return f"{scheme}{normalized}"
    if normalized.startswith(("http://", "https://")):
        return normalized
    if normalized.startswith("/"):
        return urljoin("https://www.agoda.com", normalized)
    return None


def _is_placeholder_image_url(value: str) -> bool:
    normalized = value.lower()
    return any(marker in normalized for marker in PLACEHOLDER_IMAGE_MARKERS)


def _normalize_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = " ".join(unescape(value).split())
    return normalized or None


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        normalized = _normalize_string(value)
        if normalized:
            return normalized
    return None


def _extract_amenities(
    document: dict[str, Any],
    inquiry_property: dict[str, Any] | Any,
) -> tuple[str, ...]:
    raw_values: list[Any] = [
        document.get("hotelFacilities"),
        document.get("popularFacilities"),
    ]
    if isinstance(inquiry_property, dict):
        raw_values.extend(
            [
                inquiry_property.get("facilities"),
                inquiry_property.get("hotelFacilities"),
                inquiry_property.get("popularFacilities"),
            ]
        )
    features_you_love = document.get("featuresYouLove")
    if isinstance(features_you_love, dict):
        raw_values.append(features_you_love.get("features"))

    amenities: list[str] = []
    for value in raw_values:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    normalized = _normalize_string(item)
                    if normalized:
                        amenities.append(normalized)
                elif isinstance(item, dict):
                    normalized = _normalize_string(
                        item.get("name")
                        or item.get("caption")
                        or item.get("title")
                        or item.get("text")
                    )
                    if normalized:
                        amenities.append(normalized)

    return tuple(dict.fromkeys(amenities))


def _parse_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if not isinstance(value, str):
        return None
    try:
        parsed = float(value.strip())
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


def _extract_breadcrumb_location(
    value: Any,
) -> tuple[str | None, str | None]:
    if not isinstance(value, list):
        return None, None

    names = [
        _normalize_string(item.get("regionName"))
        for item in value
        if isinstance(item, dict)
    ]
    normalized_names = [name for name in names if name]
    if not normalized_names:
        return None, None

    country_name = None
    city = None
    if len(normalized_names) >= 2:
        country_name = _strip_hotels_suffix(normalized_names[1])
    if len(normalized_names) >= 3:
        city = _strip_hotels_suffix(normalized_names[2])
    return city, country_name


def _strip_hotels_suffix(value: str) -> str:
    return re.sub(r"\s+Hotels?$", "", value, flags=re.IGNORECASE).strip()


def _extract_price_amount(
    document: dict[str, Any],
    inquiry_property: dict[str, Any] | Any,
) -> float | None:
    candidate_values: list[Any] = []
    if isinstance(inquiry_property, dict):
        candidate_values.append(inquiry_property.get("cheapestPrice"))

    sticky_footer = document.get("stickyFooter")
    if isinstance(sticky_footer, dict):
        discount = sticky_footer.get("discount")
        if isinstance(discount, dict):
            candidate_values.append(discount.get("cheapestPrice"))
            candidate_values.append(discount.get("cheapestPriceWithCurrency"))

    for candidate in candidate_values:
        amount = _parse_amount(candidate)
        if amount is not None and amount > 0:
            return amount
    return None


def _extract_price_currency(
    document: dict[str, Any],
    inquiry_property: dict[str, Any] | Any,
) -> str | None:
    currency_info = document.get("currencyInfo")
    if isinstance(currency_info, dict):
        code = _normalize_currency_code(currency_info.get("code"))
        if code:
            return code

    page_config = document.get("pageConfig")
    if isinstance(page_config, dict):
        code = _normalize_currency_code(page_config.get("currencyCode"))
        if code:
            return code

    if isinstance(inquiry_property, dict):
        return _normalize_currency_symbol(inquiry_property.get("currency"))
    return None


def _parse_amount(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^\d.]", "", value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_currency_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if len(normalized) == 3 and normalized.isalpha():
        return normalized
    return None


def _normalize_currency_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return {"$": "USD", "NT$": "TWD", "JPY": "JPY"}.get(normalized)


def _extract_availability(document: dict[str, Any]) -> tuple[bool | None, str | None]:
    room_grid_data = document.get("roomGridData")
    if isinstance(room_grid_data, dict):
        master_rooms = room_grid_data.get("masterRooms")
        if isinstance(master_rooms, list) and master_rooms:
            return False, "agoda_secondary_data_room_grid"

    number_of_fit_room = document.get("numberOfFitRoom")
    if isinstance(number_of_fit_room, int) and number_of_fit_room > 0:
        return False, "agoda_secondary_data_room_grid"

    sold_out_texts = (
        _read_nested_string(document, "soldOut", "headline"),
        _read_nested_string(document, "stickyFooter", "soldOut"),
        _read_nested_string(document, "propertyLicenseMissing", "noLicense"),
        _read_nested_string(document, "masterSoldOutRoom", "soldOutForYourDate"),
    )
    if any(_contains_sold_out_text(value) for value in sold_out_texts):
        return True, "agoda_secondary_data_sold_out"

    return None, None


def _read_nested_string(document: dict[str, Any], *keys: str) -> str | None:
    current: Any = document
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _normalize_string(current)


def _contains_sold_out_text(value: str | None) -> bool:
    if value is None:
        return False
    return SOLD_OUT_TEXT_PATTERN.search(value) is not None
