from __future__ import annotations

from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.lodging_links.agoda import classify_agoda_url
from app.lodging_links.booking import classify_booking_url
from app.lodging_links.common import normalize_hostname
from app.lodging_links.resolver import DEFAULT_BROWSER_HEADERS, LodgingUrlResolver
from app.map_enrichment.agoda import (
    extract_agoda_secondary_data_url,
    parse_agoda_secondary_data,
)
from app.map_enrichment.currency import PriceConverter
from app.map_enrichment.google_maps import (
    build_google_maps_search_url,
    build_google_maps_url,
)
from app.map_enrichment.html_parser import (
    parse_lodging_map,
    parse_lodging_map_from_url,
)
from app.map_enrichment.localization import localize_parsed_lodging_map
from app.map_enrichment.models import EnrichedLodgingMap, ParsedLodgingMap


class LodgingPageFetcher(Protocol):
    async def fetch(self, url: str) -> str: ...


class HttpLodgingPageFetcher:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def fetch(self, url: str) -> str:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=DEFAULT_BROWSER_HEADERS,
            timeout=self.timeout,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text


class LodgingMapEnrichmentService:
    def __init__(
        self,
        fetcher: LodgingPageFetcher,
        url_resolver: LodgingUrlResolver | None = None,
        price_converter: PriceConverter | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.url_resolver = url_resolver
        self.price_converter = price_converter

    async def enrich(self, url: str) -> EnrichedLodgingMap | None:
        target_url = await self._resolve_target_url(url)
        html = await self.fetcher.fetch(target_url)
        parsed = parse_lodging_map(html)
        agoda_parsed = await self._parse_agoda_secondary_data(target_url, html)
        parsed = _merge_candidates(parsed, agoda_parsed)
        if parsed is None:
            parsed = parse_lodging_map_from_url(
                target_url,
                map_source=_infer_url_fallback_source(target_url, html),
            )
        if parsed is None:
            return None
        parsed = localize_parsed_lodging_map(parsed)
        (
            price_amount,
            price_currency,
            source_price_amount,
            source_price_currency,
            price_exchange_rate,
            price_exchange_rate_source,
        ) = await self._normalize_price(parsed.price_amount, parsed.price_currency)

        google_maps_url = build_google_maps_url(
            latitude=parsed.latitude,
            longitude=parsed.longitude,
            place_id=parsed.place_id,
        )
        google_maps_search_url = build_google_maps_search_url(
            query=parsed.formatted_address or parsed.property_name,
            place_id=parsed.place_id,
        )

        return EnrichedLodgingMap(
            resolved_url=target_url,
            resolved_hostname=normalize_hostname(urlsplit(target_url).hostname),
            property_name=parsed.property_name,
            formatted_address=parsed.formatted_address,
            street_address=parsed.street_address,
            district=parsed.district,
            city=parsed.city,
            region=parsed.region,
            postal_code=parsed.postal_code,
            country_name=parsed.country_name,
            country_code=parsed.country_code,
            latitude=parsed.latitude,
            longitude=parsed.longitude,
            place_id=parsed.place_id,
            google_maps_url=google_maps_url,
            google_maps_search_url=google_maps_search_url,
            map_source=parsed.map_source,
            property_type=parsed.property_type,
            room_count=parsed.room_count,
            bedroom_count=parsed.bedroom_count,
            bathroom_count=parsed.bathroom_count,
            amenities=parsed.amenities,
            details_source=parsed.details_source,
            price_amount=price_amount,
            price_currency=price_currency,
            source_price_amount=source_price_amount,
            source_price_currency=source_price_currency,
            price_exchange_rate=price_exchange_rate,
            price_exchange_rate_source=price_exchange_rate_source,
            pricing_source=parsed.pricing_source,
            is_sold_out=parsed.is_sold_out,
            availability_source=parsed.availability_source,
        )

    async def _resolve_target_url(self, url: str) -> str:
        if self.url_resolver is None:
            return url

        resolution_plan = _get_resolution_plan(url)
        if resolution_plan is None:
            return url

        classify_url, url_kind = resolution_plan
        if url_kind != "short_link":
            return url

        resolved_url = await self.url_resolver.resolve(url)
        if not resolved_url:
            return url

        if classify_url(resolved_url) == "lodging":
            return resolved_url

        return resolved_url

    async def _parse_agoda_secondary_data(
        self,
        target_url: str,
        html: str,
    ) -> ParsedLodgingMap | None:
        hostname = normalize_hostname(urlsplit(target_url).hostname)
        if hostname != "agoda.com":
            return None

        api_url = extract_agoda_secondary_data_url(html, target_url)
        if api_url is None:
            return None

        try:
            payload = await self.fetcher.fetch(api_url)
        except Exception:
            return None

        return parse_agoda_secondary_data(payload)

    async def _normalize_price(
        self,
        amount: float | None,
        currency: str | None,
    ) -> tuple[
        float | None,
        str | None,
        float | None,
        str | None,
        float | None,
        str | None,
    ]:
        if amount is None:
            return None, currency, None, None, None, None

        source_amount = amount
        source_currency = currency
        if self.price_converter is None:
            return source_amount, source_currency, source_amount, source_currency, None, None

        try:
            converted = await self.price_converter.convert(source_amount, source_currency)
        except Exception:
            return source_amount, source_currency, source_amount, source_currency, None, None

        return (
            converted.display_amount,
            converted.display_currency,
            converted.source_amount,
            converted.source_currency,
            converted.exchange_rate,
            converted.exchange_rate_source,
        )


def _get_resolution_plan(url: str) -> tuple[object, str] | None:
    agoda_kind = classify_agoda_url(url)
    if agoda_kind != "unknown":
        return classify_agoda_url, agoda_kind

    booking_kind = classify_booking_url(url)
    if booking_kind != "unknown":
        return classify_booking_url, booking_kind

    return None


def _merge_candidates(
    primary: ParsedLodgingMap | None,
    secondary: ParsedLodgingMap | None,
) -> ParsedLodgingMap | None:
    if primary is None:
        return secondary
    if secondary is None:
        return primary

    preferred = secondary if _score_candidate(secondary) > _score_candidate(primary) else primary
    fallback = primary if preferred is secondary else secondary
    is_sold_out, availability_source = _merge_sold_out(preferred, fallback)

    return ParsedLodgingMap(
        property_name=preferred.property_name or fallback.property_name,
        formatted_address=preferred.formatted_address or fallback.formatted_address,
        street_address=preferred.street_address or fallback.street_address,
        district=preferred.district or fallback.district,
        city=preferred.city or fallback.city,
        region=preferred.region or fallback.region,
        postal_code=preferred.postal_code or fallback.postal_code,
        country_name=preferred.country_name or fallback.country_name,
        country_code=preferred.country_code or fallback.country_code,
        latitude=preferred.latitude if preferred.latitude is not None else fallback.latitude,
        longitude=preferred.longitude if preferred.longitude is not None else fallback.longitude,
        place_id=preferred.place_id or fallback.place_id,
        map_source=preferred.map_source or fallback.map_source,
        property_type=preferred.property_type or fallback.property_type,
        room_count=preferred.room_count if preferred.room_count is not None else fallback.room_count,
        bedroom_count=(
            preferred.bedroom_count
            if preferred.bedroom_count is not None
            else fallback.bedroom_count
        ),
        bathroom_count=(
            preferred.bathroom_count
            if preferred.bathroom_count is not None
            else fallback.bathroom_count
        ),
        amenities=tuple(dict.fromkeys((*preferred.amenities, *fallback.amenities))),
        details_source=preferred.details_source or fallback.details_source,
        price_amount=(
            preferred.price_amount
            if preferred.price_amount is not None
            else fallback.price_amount
        ),
        price_currency=preferred.price_currency or fallback.price_currency,
        pricing_source=preferred.pricing_source or fallback.pricing_source,
        is_sold_out=is_sold_out,
        availability_source=availability_source,
    )


def _merge_sold_out(
    preferred: ParsedLodgingMap,
    fallback: ParsedLodgingMap,
) -> tuple[bool | None, str | None]:
    if preferred.is_sold_out is True or fallback.is_sold_out is True:
        if preferred.is_sold_out is True:
            return True, preferred.availability_source
        return True, fallback.availability_source

    if preferred.is_sold_out is not None:
        return preferred.is_sold_out, preferred.availability_source
    if fallback.is_sold_out is not None:
        return fallback.is_sold_out, fallback.availability_source
    return None, None


def _score_candidate(candidate: ParsedLodgingMap) -> int:
    score = 0
    if candidate.latitude is not None and candidate.longitude is not None:
        score += 4
    if candidate.formatted_address:
        score += 2
    if candidate.property_name:
        score += 1
    return score


def _infer_url_fallback_source(url: str, html: str) -> str:
    hostname = normalize_hostname(urlsplit(url).hostname)
    if hostname == "booking.com" and _looks_like_booking_challenge_page(html):
        return "booking_challenge_url_fallback"
    return "url_slug_fallback"


def _looks_like_booking_challenge_page(html: str) -> bool:
    normalized_html = html.lower()
    return (
        "__challenge" in normalized_html
        or "challenge-container" in normalized_html
        or "reportchallengeerror" in normalized_html
    )
