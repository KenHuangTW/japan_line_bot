from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.models import LodgingLinkMatch

URL_PATTERN = re.compile(r"https?://[^\s<>\"]+")
TRAILING_PUNCTUATION = ".,!?)]}"


def extract_lodging_links(
    text: str,
    supported_domains: tuple[str, ...],
) -> list[LodgingLinkMatch]:
    if not text:
        return []

    matches: list[LodgingLinkMatch] = []
    seen_urls: set[str] = set()
    normalized_domains = tuple(domain.lower() for domain in supported_domains)

    for raw_url in URL_PATTERN.findall(text):
        candidate_url = raw_url.rstrip(TRAILING_PUNCTUATION)
        hostname = (urlsplit(candidate_url).hostname or "").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]

        matched_domain = next(
            (
                domain
                for domain in normalized_domains
                if hostname == domain or hostname.endswith(f".{domain}")
            ),
            None,
        )
        if not matched_domain or candidate_url in seen_urls:
            continue

        seen_urls.add(candidate_url)
        matches.append(
            LodgingLinkMatch(
                platform=matched_domain.split(".", maxsplit=1)[0],
                url=candidate_url,
                hostname=hostname,
            )
        )

    return matches
