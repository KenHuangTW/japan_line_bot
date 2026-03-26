from __future__ import annotations

from urllib.parse import urlencode

GOOGLE_MAPS_SEARCH_BASE_URL = "https://www.google.com/maps/search/"


def build_google_maps_url(
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    place_id: str | None = None,
) -> str | None:
    if latitude is None or longitude is None:
        return None

    query_value = f"{latitude},{longitude}"

    params = {
        "api": "1",
        "query": query_value,
    }
    if place_id:
        params["query_place_id"] = place_id.strip()

    return f"{GOOGLE_MAPS_SEARCH_BASE_URL}?{urlencode(params)}"
