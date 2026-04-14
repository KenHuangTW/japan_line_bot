from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"
logger = logging.getLogger(__name__)


class LineClient(Protocol):
    async def reply_messages(
        self,
        reply_token: str,
        messages: list[dict[str, Any]],
    ) -> None: ...

    async def reply_text(self, reply_token: str, text: str) -> None: ...


class NoopLineClient:
    async def reply_messages(
        self,
        reply_token: str,
        messages: list[dict[str, Any]],
    ) -> None:
        return None

    async def reply_text(self, reply_token: str, text: str) -> None:
        return None


class HttpLineClient:
    def __init__(
        self,
        channel_access_token: str,
        timeout: float = 10.0,
    ) -> None:
        self.channel_access_token = channel_access_token
        self.timeout = timeout

    async def reply_messages(
        self,
        reply_token: str,
        messages: list[dict[str, Any]],
    ) -> None:
        payload = {
            "replyToken": reply_token,
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {self.channel_access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                LINE_REPLY_ENDPOINT,
                headers=headers,
                json=payload,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "LINE reply API rejected messages: status=%s body=%s messages=%s",
                    exc.response.status_code,
                    exc.response.text,
                    messages,
                )
                raise

    async def reply_text(self, reply_token: str, text: str) -> None:
        await self.reply_messages(
            reply_token,
            [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        )
