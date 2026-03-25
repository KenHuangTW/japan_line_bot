from __future__ import annotations

from typing import Protocol

import httpx

DEFAULT_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    )
}


class LodgingUrlResolver(Protocol):
    async def resolve(self, url: str) -> str | None: ...


class HttpLodgingUrlResolver:
    def __init__(
        self,
        timeout: float = 10.0,
    ) -> None:
        self.timeout = timeout

    async def resolve(self, url: str) -> str | None:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=DEFAULT_BROWSER_HEADERS,
            timeout=self.timeout,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return str(response.url)
