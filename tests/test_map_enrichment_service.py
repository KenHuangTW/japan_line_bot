from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlsplit

from app.lodging_links.resolver import DEFAULT_BROWSER_HEADERS
from app.map_enrichment.currency import ConvertedPrice
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


class FakePriceConverter:
    def __init__(self, rates: dict[str, float]) -> None:
        self.rates = rates

    async def convert(self, amount: float, currency: str | None) -> ConvertedPrice:
        normalized_currency = (currency or "").upper() or None
        if normalized_currency is None:
            return ConvertedPrice(
                source_amount=amount,
                source_currency=None,
                display_amount=amount,
                display_currency=None,
            )

        rate = self.rates.get(normalized_currency)
        if rate is None:
            return ConvertedPrice(
                source_amount=amount,
                source_currency=normalized_currency,
                display_amount=amount,
                display_currency=normalized_currency,
            )

        return ConvertedPrice(
            source_amount=amount,
            source_currency=normalized_currency,
            display_amount=round(amount * rate),
            display_currency="TWD",
            exchange_rate=rate,
            exchange_rate_source="test_rate",
        )


def test_lodging_map_enrichment_service_builds_coordinate_query() -> None:
    url = "https://www.booking.com/hotel/jp/resol.html"
    html = """
    <meta property="og:image" content="https://cdn.example.com/hotels/resol.jpg" />
    <script type="application/ld+json">
      {
        "@type": "Hotel",
        "name": "Hotel Resol Ueno",
        "address": {
          "streetAddress": "7-2-9 Ueno",
          "addressLocality": "Taito City",
          "addressCountry": "JP"
        },
        "numberOfBedrooms": 1,
        "numberOfBathroomsTotal": 1,
        "amenityFeature": [
          {"name": "Free WiFi", "value": true},
          {"name": "Parking", "value": true}
        ],
        "offers": {
          "price": "18000",
          "priceCurrency": "JPY"
        },
        "geo": {
          "latitude": 35.712345,
          "longitude": 139.778901
        }
      }
    </script>
    """
    service = LodgingMapEnrichmentService(
        FakePageFetcher({url: html}),
        price_converter=FakePriceConverter({"JPY": 0.2}),
    )

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.property_name == "Hotel Resol Ueno"
    assert enriched.hero_image_url == "https://cdn.example.com/hotels/resol.jpg"
    assert enriched.line_hero_image_url == "https://cdn.example.com/hotels/resol.jpg"
    assert enriched.city == "台東區"
    assert enriched.country_code == "JP"
    assert enriched.property_type == "飯店"
    assert enriched.bedroom_count == 1
    assert enriched.bathroom_count == 1
    assert enriched.amenities == ("Free WiFi", "停車場")
    assert enriched.price_amount == 3600
    assert enriched.price_currency == "TWD"
    assert enriched.source_price_amount == 18000
    assert enriched.source_price_currency == "JPY"
    assert enriched.price_exchange_rate == 0.2
    assert enriched.price_exchange_rate_source == "test_rate"
    assert enriched.google_maps_url is not None
    query = parse_qs(urlsplit(enriched.google_maps_url).query)
    assert query["api"] == ["1"]
    assert query["query"] == ["35.712345,139.778901"]


def test_lodging_map_enrichment_service_extracts_structured_data_image_when_meta_missing() -> None:
    url = "https://www.airbnb.com/rooms/123456789"
    html = """
    <script type="application/ld+json">
      {
        "@type": "VacationRental",
        "name": "Shinjuku Loft",
        "image": [
          {"url": "/images/shinjuku-loft.jpg"}
        ],
        "address": {
          "addressLocality": "Tokyo",
          "addressCountry": "JP"
        }
      }
    </script>
    """
    service = LodgingMapEnrichmentService(FakePageFetcher({url: html}))

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.hero_image_url == "https://www.airbnb.com/images/shinjuku-loft.jpg"
    assert enriched.line_hero_image_url == "https://www.airbnb.com/images/shinjuku-loft.jpg"


def test_lodging_map_enrichment_service_keeps_raw_image_but_drops_non_line_image() -> None:
    url = "https://www.booking.com/hotel/jp/webp-only.html"
    html = """
    <meta property="og:image" content="https://cdn.example.com/hotels/webp-only.webp" />
    <script type="application/ld+json">
      {
        "@type": "Hotel",
        "name": "WebP Hotel"
      }
    </script>
    """
    service = LodgingMapEnrichmentService(FakePageFetcher({url: html}))

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.hero_image_url == "https://cdn.example.com/hotels/webp-only.webp"
    assert enriched.line_hero_image_url is None


def test_default_browser_headers_prefer_traditional_chinese() -> None:
    assert DEFAULT_BROWSER_HEADERS["Accept-Language"].startswith("zh-TW")


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
    assert query["query"] == ["1-2-3 Sakae, 名古屋, JP"]


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
    assert enriched.map_source == "booking_challenge_url_fallback"
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
        "1-1-4 Meieki, 中村區, 名古屋, 愛知, 450-6002, 日本"
    )
    assert enriched.map_source == "booking_header_address"
    assert enriched.google_maps_url is None
    assert enriched.google_maps_search_url is not None
    query = parse_qs(urlsplit(enriched.google_maps_search_url).query)
    assert query["query"] == [
        "1-1-4 Meieki, 中村區, 名古屋, 愛知, 450-6002, 日本"
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
      "breadcrumbs": [
        {"regionName": "Home"},
        {"regionName": "Japan Hotels"},
        {"regionName": "Nagoya Hotels"}
      ],
      "inquiryProperty": {
        "placeName": "FunHome黑川-包棟一軒家 車站步行4分鐘",
        "hotelNameEnglish": "FunHome Kurokawa",
        "hotelLocation": "Nagoya Castle Nagoya, Japan",
        "propertyType": "apartment",
        "numberOfBedrooms": 2,
        "numberOfBathrooms": 1.5,
        "cheapestPrice": "12345"
      },
      "hotelFacilities": [
        {"name": "Kitchen"},
        {"name": "Washer"}
      ],
      "featuresYouLove": {
        "features": [
          {"text": "Free Wi-Fi in all rooms!"},
          {"text": "Check-in/out [express]"}
        ]
      },
      "currencyInfo": {
        "code": "JPY"
      },
      "roomGridData": {
        "masterRooms": [
          {"roomId": 1}
        ]
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
    service = LodgingMapEnrichmentService(
        fetcher,
        price_converter=FakePriceConverter({"JPY": 0.2}),
    )

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.property_name == "FunHome黑川-包棟一軒家 車站步行4分鐘"
    assert enriched.formatted_address == "名古屋城 名古屋, 日本"
    assert enriched.latitude == 35.199214935302734
    assert enriched.longitude == 136.9108123779297
    assert enriched.city == "名古屋"
    assert enriched.country_name == "日本"
    assert enriched.property_type == "公寓"
    assert enriched.bedroom_count == 2
    assert enriched.bathroom_count == 1.5
    assert enriched.amenities == (
        "廚房",
        "洗衣機",
        "全客房免費 Wi-Fi",
        "快速入住／退房",
    )
    assert enriched.price_amount == 2469
    assert enriched.price_currency == "TWD"
    assert enriched.source_price_amount == 12345
    assert enriched.source_price_currency == "JPY"
    assert enriched.price_exchange_rate == 0.2
    assert enriched.price_exchange_rate_source == "test_rate"
    assert enriched.map_source == "agoda_secondary_data_geo"
    assert enriched.is_sold_out is False
    assert enriched.availability_source == "agoda_secondary_data_room_grid"
    query = parse_qs(urlsplit(enriched.google_maps_url).query)
    assert query["query"] == ["35.199214935302734,136.9108123779297"]
    assert fetcher.calls == [url, api_url]


def test_lodging_map_enrichment_service_marks_agoda_property_as_sold_out() -> None:
    url = "https://www.agoda.com/sold-out/hotel/nagoya-jp.html"
    api_url = (
        "https://www.agoda.com/api/cronos/property/BelowFoldParams/"
        "GetSecondaryData?hotel_id=999&all=false&isHostPropertiesEnabled=false"
    )
    html = """
    <html>
      <head><title>Sold Out Stay</title></head>
      <body>
        <script type="text/javascript" data-selenium="script-initparam">
          var apiUrl="/api/cronos/property/BelowFoldParams/GetSecondaryData?hotel_id=999&amp;all=false&amp;isHostPropertiesEnabled=false";
        </script>
      </body>
    </html>
    """
    payload = """
    {
      "breadcrumbs": [
        {"regionName": "Home"},
        {"regionName": "Japan Hotels"},
        {"regionName": "Nagoya Hotels"}
      ],
      "inquiryProperty": {
        "placeName": "Sold Out Stay",
        "hotelLocation": "Nagoya, Japan"
      },
      "roomGridData": {
        "isDataReady": true,
        "masterRooms": []
      },
      "soldOut": {
        "headline": "Sold out on your dates!"
      },
      "mapParams": {
        "latlng": [35.17, 136.91]
      }
    }
    """
    fetcher = FakePageFetcher({url: html, api_url: payload})
    service = LodgingMapEnrichmentService(fetcher)

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.property_name == "Sold Out Stay"
    assert enriched.is_sold_out is True
    assert enriched.availability_source == "agoda_secondary_data_sold_out"


def test_lodging_map_enrichment_service_enriches_airbnb_structured_data() -> None:
    url = "https://www.airbnb.com/rooms/123456789"
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "VacationRental",
            "name": "Shinjuku Loft",
            "address": {
              "@type": "PostalAddress",
              "streetAddress": "1-2-3 Kabukicho",
              "addressLocality": "Tokyo",
              "addressRegion": "Tokyo",
              "addressCountry": "JP"
            },
            "numberOfBedrooms": 1,
            "numberOfBathroomsTotal": 1,
            "amenityFeature": [
              {"name": "Kitchen", "value": true},
              {"name": "Washer", "value": true}
            ],
            "offers": {
              "@type": "Offer",
              "price": "24000",
              "priceCurrency": "JPY"
            },
            "geo": {
              "@type": "GeoCoordinates",
              "latitude": 35.69384,
              "longitude": 139.70355
            }
          }
        </script>
      </head>
    </html>
    """
    service = LodgingMapEnrichmentService(
        FakePageFetcher({url: html}),
        price_converter=FakePriceConverter({"JPY": 0.2}),
    )

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.resolved_url == url
    assert enriched.resolved_hostname == "airbnb.com"
    assert enriched.property_name == "Shinjuku Loft"
    assert enriched.city == "東京"
    assert enriched.country_code == "JP"
    assert enriched.property_type == "度假出租"
    assert enriched.amenities == ("廚房", "洗衣機")
    assert enriched.price_amount == 4800
    assert enriched.price_currency == "TWD"
    assert enriched.source_price_amount == 24000
    assert enriched.source_price_currency == "JPY"
    assert enriched.map_source == "structured_data_geo"


def test_lodging_map_enrichment_service_falls_back_to_airbnb_title() -> None:
    url = "https://www.airbnb.com.tw/rooms/123456789"
    html = """
    <html>
      <head><title>Shinjuku Loft - Airbnb</title></head>
      <body><div>Limited public metadata</div></body>
    </html>
    """
    service = LodgingMapEnrichmentService(FakePageFetcher({url: html}))

    enriched = asyncio.run(service.enrich(url))

    assert enriched is not None
    assert enriched.resolved_hostname == "airbnb.com.tw"
    assert enriched.property_name == "Shinjuku Loft"
    assert enriched.latitude is None
    assert enriched.longitude is None
    assert enriched.map_source == "airbnb_html_title_fallback"
    assert enriched.google_maps_url is None
    assert enriched.google_maps_search_url is not None
    query = parse_qs(urlsplit(enriched.google_maps_search_url).query)
    assert query["query"] == ["Shinjuku Loft"]
