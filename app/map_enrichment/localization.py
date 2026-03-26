from __future__ import annotations

from app.map_enrichment.models import ParsedLodgingMap

_EXACT_TEXT_MAP = {
    "Japan": "日本",
    "Tokyo": "東京",
    "Nagoya": "名古屋",
    "Aichi": "愛知",
    "Taito City": "台東區",
    "Nakamura-ku": "中村區",
    "Meito": "名東區",
    "Nagoya Castle": "名古屋城",
    "hotel": "飯店",
    "apartment": "公寓",
    "vacationrental": "度假出租",
    "Linens": "床單",
    "Air conditioning": "空調",
    "Smoking area": "吸菸區",
    "Car park": "停車場",
    "Kitchen": "廚房",
    "Washer": "洗衣機",
    "Parking": "停車場",
    "Free Wi-Fi in all rooms!": "全客房免費 Wi-Fi",
    "Check-in/out [express]": "快速入住／退房",
    "Chinese [Mandarin]": "中文（普通話）",
    "Non-smoking rooms": "禁菸客房",
    "240 meters to public transportation": "距離大眾運輸 240 公尺",
}

_SUBSTRING_TEXT_MAP = {
    "Nagoya Castle": "名古屋城",
    "Taito City": "台東區",
    "Nakamura-ku": "中村區",
    "Meito": "名東區",
    "Aichi": "愛知",
    "Nagoya": "名古屋",
    "Tokyo": "東京",
    "Japan": "日本",
}


def localize_parsed_lodging_map(parsed: ParsedLodgingMap) -> ParsedLodgingMap:
    return ParsedLodgingMap(
        property_name=parsed.property_name,
        formatted_address=_localize_address(parsed.formatted_address),
        street_address=_localize_address(parsed.street_address),
        district=_localize_text(parsed.district),
        city=_localize_text(parsed.city),
        region=_localize_text(parsed.region),
        postal_code=parsed.postal_code,
        country_name=_localize_text(parsed.country_name),
        country_code=parsed.country_code,
        latitude=parsed.latitude,
        longitude=parsed.longitude,
        place_id=parsed.place_id,
        map_source=parsed.map_source,
        property_type=_localize_text(parsed.property_type),
        room_count=parsed.room_count,
        bedroom_count=parsed.bedroom_count,
        bathroom_count=parsed.bathroom_count,
        amenities=_localize_amenities(parsed.amenities),
        details_source=parsed.details_source,
        price_amount=parsed.price_amount,
        price_currency=parsed.price_currency,
        pricing_source=parsed.pricing_source,
        is_sold_out=parsed.is_sold_out,
        availability_source=parsed.availability_source,
    )


def _localize_amenities(values: tuple[str, ...]) -> tuple[str, ...]:
    localized_values = [_localize_text(value) or value for value in values]
    return tuple(dict.fromkeys(localized_values))


def _localize_address(value: str | None) -> str | None:
    if value is None:
        return None

    localized = value
    for source, target in _SUBSTRING_TEXT_MAP.items():
        localized = localized.replace(source, target)
    return localized


def _localize_text(value: str | None) -> str | None:
    if value is None:
        return None
    exact_match = _EXACT_TEXT_MAP.get(value)
    if exact_match is not None:
        return exact_match

    localized = value
    for source, target in _SUBSTRING_TEXT_MAP.items():
        localized = localized.replace(source, target)
    return localized
