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
from app.map_enrichment.google_maps import build_google_maps_url
from app.map_enrichment.html_parser import (
    parse_lodging_map,
    parse_lodging_map_from_url,
)
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
    ) -> None:
        self.fetcher = fetcher
        self.url_resolver = url_resolver

    async def enrich(self, url: str) -> EnrichedLodgingMap | None:
        target_url = await self._resolve_target_url(url)
        html = await self.fetcher.fetch(target_url)
        parsed = parse_lodging_map(html)
        agoda_parsed = await self._parse_agoda_secondary_data(target_url, html)
        parsed = _choose_better_candidate(parsed, agoda_parsed)
        if parsed is None:
            parsed = parse_lodging_map_from_url(target_url)
        if parsed is None:
            return None

        google_maps_url = build_google_maps_url(
            latitude=parsed.latitude,
            longitude=parsed.longitude,
            query=parsed.formatted_address or parsed.property_name,
            place_id=parsed.place_id,
        )
        if google_maps_url is None:
            return None

        return EnrichedLodgingMap(
            resolved_url=target_url,
            resolved_hostname=normalize_hostname(urlsplit(target_url).hostname),
            property_name=parsed.property_name,
            formatted_address=parsed.formatted_address,
            latitude=parsed.latitude,
            longitude=parsed.longitude,
            place_id=parsed.place_id,
            google_maps_url=google_maps_url,
            map_source=parsed.map_source,
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


def _get_resolution_plan(url: str) -> tuple[object, str] | None:
    agoda_kind = classify_agoda_url(url)
    if agoda_kind != "unknown":
        return classify_agoda_url, agoda_kind

    booking_kind = classify_booking_url(url)
    if booking_kind != "unknown":
        return classify_booking_url, booking_kind

    return None


def _choose_better_candidate(
    primary: ParsedLodgingMap | None,
    secondary: ParsedLodgingMap | None,
) -> ParsedLodgingMap | None:
    if primary is None:
        return secondary
    if secondary is None:
        return primary

    return secondary if _score_candidate(secondary) > _score_candidate(primary) else primary


def _score_candidate(candidate: ParsedLodgingMap) -> int:
    score = 0
    if candidate.latitude is not None and candidate.longitude is not None:
        score += 4
    if candidate.formatted_address:
        score += 2
    if candidate.property_name:
        score += 1
    return score
