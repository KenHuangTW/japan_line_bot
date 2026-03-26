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
              "addressLocality": "Taito City",
              "addressRegion": "Tokyo",
              "postalCode": "110-0005",
              "addressCountry": "JP"
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
    assert parsed.latitude == 35.712345
    assert parsed.longitude == 139.778901
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
