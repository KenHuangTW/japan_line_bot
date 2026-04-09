from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from app.lodging_links.common import normalize_hostname

AIRBNB_BASE_HOSTNAMES = ("airbnb.com", "airbnb.com.tw")
AIRBNB_NON_LODGING_PATH_PREFIXES = (
    "/categories",
    "/experiences",
    "/help",
    "/hosting",
    "/rooms",
    "/s",
    "/services",
    "/users",
    "/wishlists",
)
AIRBNB_LOCALE_SEGMENT_PATTERN = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")
AIRBNB_ROOM_ID_PATTERN = re.compile(r"^\d+$")

AirbnbUrlKind = Literal["lodging", "non_lodging", "unknown"]


def is_airbnb_hostname(hostname: str | None) -> bool:
    normalized = normalize_hostname(hostname)
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in AIRBNB_BASE_HOSTNAMES
    )


def is_airbnb_lodging_url(url: str) -> bool:
    parsed = urlsplit(url)
    if not is_airbnb_hostname(parsed.hostname):
        return False

    segments = _normalized_path_segments(parsed.path)
    return (
        len(segments) == 2
        and segments[0] == "rooms"
        and AIRBNB_ROOM_ID_PATTERN.fullmatch(segments[1]) is not None
    )


def is_airbnb_non_lodging_url(url: str) -> bool:
    parsed = urlsplit(url)
    if not is_airbnb_hostname(parsed.hostname):
        return False

    normalized_path = _normalized_path(parsed.path)
    return any(
        normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
        for prefix in AIRBNB_NON_LODGING_PATH_PREFIXES
        if prefix != "/rooms"
    ) or (
        normalized_path.startswith("/rooms/")
        and not is_airbnb_lodging_url(url)
    )


def classify_airbnb_url(url: str) -> AirbnbUrlKind:
    if is_airbnb_lodging_url(url):
        return "lodging"
    if is_airbnb_non_lodging_url(url):
        return "non_lodging"
    return "unknown"


def _normalized_path_segments(path: str) -> list[str]:
    segments = [segment.lower() for segment in path.split("/") if segment]
    if segments and AIRBNB_LOCALE_SEGMENT_PATTERN.fullmatch(segments[0]) is not None:
        return segments[1:]
    return segments


def _normalized_path(path: str) -> str:
    segments = _normalized_path_segments(path)
    if not segments:
        return "/"
    return "/" + "/".join(segments)
