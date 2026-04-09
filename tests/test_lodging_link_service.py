from __future__ import annotations

import asyncio

from app.lodging_links.service import LodgingLinkService
from app.models import LodgingLinkMatch


class FakeLodgingUrlResolver:
    def __init__(
        self,
        resolved_urls: dict[str, str | None] | None = None,
        failing_urls: set[str] | None = None,
    ) -> None:
        self.resolved_urls = resolved_urls or {}
        self.failing_urls = failing_urls or set()
        self.calls: list[str] = []

    async def resolve(self, url: str) -> str | None:
        self.calls.append(url)
        if url in self.failing_urls:
            raise RuntimeError("simulated resolver failure")
        return self.resolved_urls.get(url)


def test_lodging_link_service_keeps_direct_lodging_links() -> None:
    resolver = FakeLodgingUrlResolver()
    service = LodgingLinkService(resolver)
    matches = [
        LodgingLinkMatch(
            platform="booking",
            url="https://www.booking.com/hotel/jp/foo.html",
            hostname="booking.com",
        ),
        LodgingLinkMatch(
            platform="agoda",
            url="https://www.agoda.com/zh-tw/bar-hotel/hotel/tokyo-jp.html",
            hostname="agoda.com",
        ),
        LodgingLinkMatch(
            platform="airbnb",
            url="https://www.airbnb.com/ja/rooms/123456789?check_in=2026-04-10",
            hostname="airbnb.com",
        ),
    ]

    resolved_matches = asyncio.run(service.filter_supported_lodging_links(matches))

    assert [item.url for item in resolved_matches] == [
        "https://www.booking.com/hotel/jp/foo.html",
        "https://www.agoda.com/zh-tw/bar-hotel/hotel/tokyo-jp.html",
        "https://www.airbnb.com/ja/rooms/123456789?check_in=2026-04-10",
    ]
    assert [item.resolved_url for item in resolved_matches] == [
        "https://www.booking.com/hotel/jp/foo.html",
        "https://www.agoda.com/zh-tw/bar-hotel/hotel/tokyo-jp.html",
        "https://www.airbnb.com/ja/rooms/123456789?check_in=2026-04-10",
    ]
    assert resolver.calls == []


def test_lodging_link_service_filters_non_lodging_agoda_links() -> None:
    resolver = FakeLodgingUrlResolver()
    service = LodgingLinkService(resolver)
    matches = [
        LodgingLinkMatch(
            platform="agoda",
            url="https://www.agoda.com/activities/detail?cid=1",
            hostname="agoda.com",
        ),
        LodgingLinkMatch(
            platform="agoda",
            url="https://www.agoda.com/travel-guides/japan/tokyo",
            hostname="agoda.com",
        ),
    ]

    resolved_matches = asyncio.run(service.filter_supported_lodging_links(matches))

    assert resolved_matches == []
    assert resolver.calls == []


def test_lodging_link_service_filters_non_lodging_booking_links() -> None:
    resolver = FakeLodgingUrlResolver()
    service = LodgingLinkService(resolver)
    matches = [
        LodgingLinkMatch(
            platform="booking",
            url="https://www.booking.com/searchresults.zh-tw.html?ss=Tokyo",
            hostname="booking.com",
        )
    ]

    resolved_matches = asyncio.run(service.filter_supported_lodging_links(matches))

    assert resolved_matches == []
    assert resolver.calls == []


def test_lodging_link_service_filters_non_lodging_airbnb_links() -> None:
    resolver = FakeLodgingUrlResolver()
    service = LodgingLinkService(resolver)
    matches = [
        LodgingLinkMatch(
            platform="airbnb",
            url="https://www.airbnb.com/s/Tokyo/homes",
            hostname="airbnb.com",
        ),
        LodgingLinkMatch(
            platform="airbnb",
            url="https://www.airbnb.com/wishlists/123456789",
            hostname="airbnb.com",
        ),
    ]

    resolved_matches = asyncio.run(service.filter_supported_lodging_links(matches))

    assert resolved_matches == []
    assert resolver.calls == []


def test_lodging_link_service_resolves_agoda_short_links() -> None:
    short_url = "https://www.agoda.com/sp/B70FF37xamn"
    resolved_url = (
        "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
        "?pid=redirect"
    )
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    service = LodgingLinkService(resolver)
    matches = [
        LodgingLinkMatch(
            platform="agoda",
            url=short_url,
            hostname="agoda.com",
        )
    ]

    resolved_matches = asyncio.run(service.filter_supported_lodging_links(matches))

    assert len(resolved_matches) == 1
    assert resolved_matches[0].url == short_url
    assert resolved_matches[0].resolved_url == resolved_url
    assert resolved_matches[0].resolved_hostname == "agoda.com"
    assert resolver.calls == [short_url]


def test_lodging_link_service_resolves_booking_short_links() -> None:
    short_url = "https://www.booking.com/Share-08PTGo"
    resolved_url = "https://www.booking.com/hotel/jp/hotel-resol-ueno.zh-tw.html"
    resolver = FakeLodgingUrlResolver(resolved_urls={short_url: resolved_url})
    service = LodgingLinkService(resolver)
    matches = [
        LodgingLinkMatch(
            platform="booking",
            url=short_url,
            hostname="booking.com",
        )
    ]

    resolved_matches = asyncio.run(service.filter_supported_lodging_links(matches))

    assert len(resolved_matches) == 1
    assert resolved_matches[0].url == short_url
    assert resolved_matches[0].resolved_url == resolved_url
    assert resolved_matches[0].resolved_hostname == "booking.com"
    assert resolver.calls == [short_url]


def test_lodging_link_service_drops_unresolved_agoda_short_links() -> None:
    short_url = "https://www.agoda.com/sp/not-a-lodging-link"
    resolver = FakeLodgingUrlResolver(
        resolved_urls={short_url: "https://www.agoda.com/activities"},
    )
    service = LodgingLinkService(resolver)
    matches = [
        LodgingLinkMatch(
            platform="agoda",
            url=short_url,
            hostname="agoda.com",
        )
    ]

    resolved_matches = asyncio.run(service.filter_supported_lodging_links(matches))

    assert resolved_matches == []
    assert resolver.calls == [short_url]
