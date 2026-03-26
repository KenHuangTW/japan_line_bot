from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlsplit

from app.map_enrichment.service import LodgingMapEnrichmentService


class FakePageFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    async def fetch(self, url: str) -> str:
        self.calls.append(url)
        return self.pages[url]


class FakeUrlResolver:
    def __init__(self, resolved_urls: dict[str, str]) -> None:
        self.resolved_urls = resolved_urls
        self.calls: list[str] = []

    async def resolve(self, url: str) -> str | None:
        self.calls.append(url)
        return self.resolved_urls.get(url)


def test_lodging_map_enrichment_service_builds_coordinate_query() -> None:
    url = "https://www.booking.com/hotel/jp/resol.html"
    html = """
    <script type="application/ld+json">
      {
        "@type": "Hotel",
        "name": "Hotel Resol Ueno",
        "address": {
          "streetAddress": "7-2-9 Ueno",
          "addressLocality": "Taito City",
          "addressCountry": "JP"
        },
        "geo": {
          "latitude": 35.712345,
          "longitude": 139.778901
        }
      }
    </script>
    """
    service = LodgingMapEnrichmentService(FakePageFetcher({url: html}))

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.property_name == "Hotel Resol Ueno"
    assert enriched.google_maps_url is not None
    query = parse_qs(urlsplit(enriched.google_maps_url).query)
    assert query["api"] == ["1"]
    assert query["query"] == ["35.712345,139.778901"]


def test_lodging_map_enrichment_service_falls_back_to_address_query() -> None:
    url = "https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html"
    html = """
    <script type="application/ld+json">
      {
        "@type": "Hotel",
        "name": "Nagoya Stay",
        "address": {
          "streetAddress": "1-2-3 Sakae",
          "addressLocality": "Nagoya",
          "addressCountry": "JP"
        }
      }
    </script>
    """
    service = LodgingMapEnrichmentService(FakePageFetcher({url: html}))

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.latitude is None
    assert enriched.longitude is None
    assert enriched.google_maps_url is None
    assert enriched.google_maps_search_url is not None
    query = parse_qs(urlsplit(enriched.google_maps_search_url).query)
    assert query["query"] == ["1-2-3 Sakae, Nagoya, JP"]


def test_lodging_map_enrichment_service_falls_back_to_url_slug_when_page_is_blocked() -> None:
    url = "https://www.booking.com/hotel/jp/nagoya-marriott-associa.zh-tw.html"
    html = """
    <html>
      <head><title></title></head>
      <body>
        <div id="challenge-container"></div>
        <script src="https://www.booking.com/__challenge/example/challenge.js"></script>
      </body>
    </html>
    """
    service = LodgingMapEnrichmentService(FakePageFetcher({url: html}))

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.property_name == "Nagoya Marriott Associa"
    assert enriched.map_source == "url_slug_fallback"
    assert enriched.google_maps_url is None
    assert enriched.google_maps_search_url is not None
    query = parse_qs(urlsplit(enriched.google_maps_search_url).query)
    assert query["query"] == ["Nagoya Marriott Associa"]


def test_lodging_map_enrichment_service_uses_booking_header_address_when_available() -> None:
    url = "https://www.booking.com/hotel/jp/nagoya-marriott-associa.zh-tw.html"
    html = """
    <html>
      <head>
        <title>Nagoya Marriott Associa Hotel | Booking.com</title>
      </head>
      <body>
        <span data-testid="PropertyHeaderAddressDesktop">
          1-1-4 Meieki, Nakamura-ku, Nagoya, Aichi, 450-6002, Japan
        </span>
      </body>
    </html>
    """
    service = LodgingMapEnrichmentService(FakePageFetcher({url: html}))

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.property_name == "Nagoya Marriott Associa Hotel"
    assert enriched.formatted_address == (
        "1-1-4 Meieki, Nakamura-ku, Nagoya, Aichi, 450-6002, Japan"
    )
    assert enriched.map_source == "booking_header_address"
    assert enriched.google_maps_url is None
    assert enriched.google_maps_search_url is not None
    query = parse_qs(urlsplit(enriched.google_maps_search_url).query)
    assert query["query"] == [
        "1-1-4 Meieki, Nakamura-ku, Nagoya, Aichi, 450-6002, Japan"
    ]


def test_lodging_map_enrichment_service_resolves_agoda_short_link_before_fetching() -> None:
    short_url = "https://www.agoda.com/sp/B70FF37xamn"
    resolved_url = "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
    html = """
    <html>
      <head><title></title></head>
      <body>
        <div id="challenge-container"></div>
      </body>
    </html>
    """
    fetcher = FakePageFetcher({resolved_url: html})
    resolver = FakeUrlResolver({short_url: resolved_url})
    service = LodgingMapEnrichmentService(fetcher, resolver)

    enriched = asyncio.run(service.enrich(short_url))

    assert enriched is not None
    assert enriched.resolved_url == resolved_url
    assert enriched.resolved_hostname == "agoda.com"
    assert enriched.property_name == "Funhome H40642218"
    assert enriched.map_source == "url_slug_fallback"
    assert resolver.calls == [short_url]
    assert fetcher.calls == [resolved_url]


def test_lodging_map_enrichment_service_prefers_agoda_secondary_data_coordinates() -> None:
    url = "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
    api_url = (
        "https://www.agoda.com/api/cronos/property/BelowFoldParams/"
        "GetSecondaryData?hotel_id=40642218&all=false&isHostPropertiesEnabled=false"
    )
    html = """
    <html>
      <head><title></title></head>
      <body>
        <script type="text/javascript" data-selenium="script-initparam">
          var apiUrl="/api/cronos/property/BelowFoldParams/GetSecondaryData?hotel_id=40642218&amp;all=false&amp;isHostPropertiesEnabled=false";
        </script>
      </body>
    </html>
    """
    payload = """
    {
      "inquiryProperty": {
        "hotelNameEnglish": "FunHome Kurokawa",
        "hotelLocation": "Nagoya Castle Nagoya, Japan"
      },
      "mapParams": {
        "latlng": [35.199214935302734, 136.9108123779297]
      }
    }
    """
    fetcher = FakePageFetcher(
        {
            url: html,
            api_url: payload,
        }
    )
    service = LodgingMapEnrichmentService(fetcher)

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.property_name == "FunHome Kurokawa"
    assert enriched.formatted_address == "Nagoya Castle Nagoya, Japan"
    assert enriched.latitude == 35.199214935302734
    assert enriched.longitude == 136.9108123779297
    assert enriched.map_source == "agoda_secondary_data_geo"
    query = parse_qs(urlsplit(enriched.google_maps_url).query)
    assert query["query"] == ["35.199214935302734,136.9108123779297"]
    assert fetcher.calls == [url, api_url]
