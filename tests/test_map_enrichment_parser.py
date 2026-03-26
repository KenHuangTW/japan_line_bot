from __future__ import annotations

from app.map_enrichment.html_parser import parse_lodging_map


def test_parse_lodging_map_extracts_structured_data_hotel() -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Hotel",
            "name": "Hotel Resol Ueno",
            "address": {
              "@type": "PostalAddress",
              "streetAddress": "7-2-9 Ueno",
              "district": "Taito City",
              "addressLocality": "Taito City",
              "addressRegion": "Tokyo",
              "postalCode": "110-0005",
              "addressCountry": "JP"
            },
            "numberOfRooms": 1,
            "numberOfBedrooms": 1,
            "numberOfBathroomsTotal": 1.5,
            "amenityFeature": [
              {
                "@type": "LocationFeatureSpecification",
                "name": "Free WiFi",
                "value": true
              },
              {
                "@type": "LocationFeatureSpecification",
                "name": "Breakfast",
                "value": false
              }
            ],
            "offers": {
              "@type": "Offer",
              "price": "18000",
              "priceCurrency": "JPY"
            },
            "geo": {
              "@type": "GeoCoordinates",
              "latitude": 35.712345,
              "longitude": 139.778901
            }
          }
        </script>
      </head>
    </html>
    """

    parsed = parse_lodging_map(html)

    assert parsed is not None
    assert parsed.property_name == "Hotel Resol Ueno"
    assert parsed.formatted_address == "7-2-9 Ueno, Taito City, Tokyo, 110-0005, JP"
    assert parsed.street_address == "7-2-9 Ueno"
    assert parsed.district == "Taito City"
    assert parsed.city == "Taito City"
    assert parsed.region == "Tokyo"
    assert parsed.postal_code == "110-0005"
    assert parsed.country_code == "JP"
    assert parsed.latitude == 35.712345
    assert parsed.longitude == 139.778901
    assert parsed.property_type == "hotel"
    assert parsed.room_count == 1
    assert parsed.bedroom_count == 1
    assert parsed.bathroom_count == 1.5
    assert parsed.amenities == ("Free WiFi",)
    assert parsed.price_amount == 18000
    assert parsed.price_currency == "JPY"
    assert parsed.details_source == "structured_data_details"
    assert parsed.pricing_source == "structured_data_offer"
    assert parsed.map_source == "structured_data_geo"


def test_parse_lodging_map_falls_back_to_regex_coordinates() -> None:
    html = """
    <html>
      <head>
        <title>Tokyo Stay</title>
      </head>
      <body>
        <script>
          window.__STATE__ = {
            "latitude": "35.6895",
            "longitude": "139.6917"
          };
        </script>
      </body>
    </html>
    """

    parsed = parse_lodging_map(html)

    assert parsed is not None
    assert parsed.property_name == "Tokyo Stay"
    assert parsed.latitude == 35.6895
    assert parsed.longitude == 139.6917
    assert parsed.map_source == "html_regex_geo"


def test_parse_lodging_map_detects_visible_sold_out_message() -> None:
    html = """
    <html>
      <head>
        <title>Tokyo Stay</title>
        <script>
          const translations = { soldOut: "Sold out on your dates!" };
        </script>
      </head>
      <body>
        <div class="availability-banner">這間住宿已無空房</div>
      </body>
    </html>
    """

    parsed = parse_lodging_map(html)

    assert parsed is not None
    assert parsed.property_name == "Tokyo Stay"
    assert parsed.is_sold_out is True
    assert parsed.availability_source == "html_visible_text_sold_out"
