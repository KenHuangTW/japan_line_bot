from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from app.lodging_links.common import normalize_hostname

BookingUrlKind = Literal["lodging", "short_link", "unknown"]
BOOKING_SHORT_LINK_PREFIX = "/share-"


def is_booking_hostname(hostname: str | None) -> bool:
    normalized = normalize_hostname(hostname)
    return normalized == "booking.com" or normalized.endswith(".booking.com")


def is_booking_lodging_url(url: str) -> bool:
    parsed = urlsplit(url)
    if not is_booking_hostname(parsed.hostname):
        return False

    path = parsed.path.lower()
    return path.startswith("/hotel/") and path.endswith(".html")


def is_booking_short_link(url: str) -> bool:
    parsed = urlsplit(url)
    if not is_booking_hostname(parsed.hostname):
        return False

    path = parsed.path.lower()
    return path.startswith(BOOKING_SHORT_LINK_PREFIX) and len(path) > len(
        BOOKING_SHORT_LINK_PREFIX
    )


def classify_booking_url(url: str) -> BookingUrlKind:
    if is_booking_lodging_url(url):
        return "lodging"
    if is_booking_short_link(url):
        return "short_link"
    return "unknown"
