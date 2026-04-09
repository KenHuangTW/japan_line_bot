from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlsplit

from app.lodging_links.agoda import is_agoda_hostname
from app.lodging_links.airbnb import is_airbnb_hostname
from app.lodging_links.booking import is_booking_hostname
from app.lodging_links.common import normalize_hostname
from app.models import LodgingLinkMatch

URL_PATTERN = re.compile(r"https?://[^\s<>\"]+")
TRAILING_PUNCTUATION = ".,!?)]}"
HostnameMatcher = Callable[[str | None], bool]
PLATFORM_HOSTNAME_MATCHERS = (
    ("booking", is_booking_hostname),
    ("agoda", is_agoda_hostname),
    ("airbnb", is_airbnb_hostname),
)


def extract_lodging_links(
    text: str,
    supported_domains: tuple[str, ...],
) -> list[LodgingLinkMatch]:
    if not text:
        return []

    matches: list[LodgingLinkMatch] = []
    seen_urls: set[str] = set()
    enabled_platform_matchers = _build_enabled_platform_matchers(supported_domains)
    if not enabled_platform_matchers:
        return []

    for raw_url in URL_PATTERN.findall(text):
        candidate_url = raw_url.rstrip(TRAILING_PUNCTUATION)
        hostname = normalize_hostname(urlsplit(candidate_url).hostname)
        matched_platform = next(
            (
                platform
                for platform, hostname_matcher in enabled_platform_matchers
                if hostname_matcher(hostname)
            ),
            None,
        )
        if not matched_platform or candidate_url in seen_urls:
            continue

        seen_urls.add(candidate_url)
        matches.append(
            LodgingLinkMatch(
                platform=matched_platform,
                url=candidate_url,
                hostname=hostname,
            )
        )

    return matches


def _build_enabled_platform_matchers(
    supported_domains: tuple[str, ...],
) -> tuple[tuple[str, HostnameMatcher], ...]:
    normalized_domains = tuple(domain.lower() for domain in supported_domains)
    enabled: list[tuple[str, HostnameMatcher]] = []

    for platform, hostname_matcher in PLATFORM_HOSTNAME_MATCHERS:
        if any(hostname_matcher(domain) for domain in normalized_domains):
            enabled.append((platform, hostname_matcher))

    return tuple(enabled)
