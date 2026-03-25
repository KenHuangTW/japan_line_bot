from __future__ import annotations

import logging
from typing import Sequence
from urllib.parse import urlsplit

from app.lodging_links.agoda import classify_agoda_url, normalize_hostname
from app.lodging_links.resolver import LodgingUrlResolver
from app.models import LodgingLinkMatch

logger = logging.getLogger(__name__)


class LodgingLinkService:
    def __init__(self, resolver: LodgingUrlResolver) -> None:
        self.resolver = resolver

    async def filter_supported_lodging_links(
        self,
        matches: Sequence[LodgingLinkMatch],
    ) -> list[LodgingLinkMatch]:
        lodging_links: list[LodgingLinkMatch] = []

        for match in matches:
            resolved_match = await self._resolve_match(match)
            if resolved_match is not None:
                lodging_links.append(resolved_match)

        return lodging_links

    async def _resolve_match(
        self,
        match: LodgingLinkMatch,
    ) -> LodgingLinkMatch | None:
        if match.platform != "agoda":
            return self._with_resolved_url(
                match,
                resolved_url=match.url,
                resolved_hostname=match.hostname,
            )

        agoda_url_kind = classify_agoda_url(match.url)
        if agoda_url_kind == "lodging":
            return self._with_resolved_url(
                match,
                resolved_url=match.url,
                resolved_hostname=match.hostname,
            )
        if agoda_url_kind != "short_link":
            return None

        try:
            resolved_url = await self.resolver.resolve(match.url)
        except Exception:
            logger.exception("Failed to resolve Agoda share URL: %s", match.url)
            return None

        if not resolved_url or classify_agoda_url(resolved_url) != "lodging":
            return None

        return self._with_resolved_url(
            match,
            resolved_url=resolved_url,
            resolved_hostname=normalize_hostname(urlsplit(resolved_url).hostname),
        )

    def _with_resolved_url(
        self,
        match: LodgingLinkMatch,
        resolved_url: str,
        resolved_hostname: str,
    ) -> LodgingLinkMatch:
        return match.model_copy(
            update={
                "resolved_url": resolved_url,
                "resolved_hostname": resolved_hostname,
            }
        )
