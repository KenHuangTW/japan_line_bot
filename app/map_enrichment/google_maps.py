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
    return _build_search_url(query_value=query_value, place_id=place_id)


def build_google_maps_search_url(
    *,
    query: str | None = None,
    place_id: str | None = None,
) -> str | None:
    query_value = (query or "").strip()
    if not query_value:
        return None

    return _build_search_url(query_value=query_value, place_id=place_id)


def _build_search_url(*, query_value: str, place_id: str | None = None) -> str:
    params = {
        "api": "1",
        "query": query_value,
    }
    if place_id:
        params["query_place_id"] = place_id.strip()

    return f"{GOOGLE_MAPS_SEARCH_BASE_URL}?{urlencode(params)}"
