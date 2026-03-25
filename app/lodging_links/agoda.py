from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

AGODA_NON_LODGING_PATH_PREFIXES = (
    "/activities",
    "/blog",
    "/cars",
    "/flights",
    "/info",
    "/travel-guides",
)
AGODA_SHORT_LINK_PREFIX = "/sp/"

AgodaUrlKind = Literal["lodging", "short_link", "non_lodging", "unknown"]


def normalize_hostname(hostname: str | None) -> str:
    normalized = (hostname or "").lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def is_agoda_hostname(hostname: str | None) -> bool:
    normalized = normalize_hostname(hostname)
    return normalized == "agoda.com" or normalized.endswith(".agoda.com")


def is_agoda_lodging_url(url: str) -> bool:
    parsed = urlsplit(url)
    if not is_agoda_hostname(parsed.hostname):
        return False

    path = parsed.path.lower()
    return "/hotel/" in path and path.endswith(".html")


def is_agoda_short_link(url: str) -> bool:
    parsed = urlsplit(url)
    if not is_agoda_hostname(parsed.hostname):
        return False

    path = parsed.path.lower()
    return path.startswith(AGODA_SHORT_LINK_PREFIX) and len(path) > len(
        AGODA_SHORT_LINK_PREFIX
    )


def is_agoda_non_lodging_url(url: str) -> bool:
    parsed = urlsplit(url)
    if not is_agoda_hostname(parsed.hostname):
        return False

    path = parsed.path.lower()
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in AGODA_NON_LODGING_PATH_PREFIXES
    )


def classify_agoda_url(url: str) -> AgodaUrlKind:
    if is_agoda_lodging_url(url):
        return "lodging"
    if is_agoda_short_link(url):
        return "short_link"
    if is_agoda_non_lodging_url(url):
        return "non_lodging"
    return "unknown"
