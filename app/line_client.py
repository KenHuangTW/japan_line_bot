from __future__ import annotations

from typing import Protocol

import httpx

LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"


class LineClient(Protocol):
    async def reply_text(self, reply_token: str, text: str) -> None:
        ...


class NoopLineClient:
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

    async def reply_text(self, reply_token: str, text: str) -> None:
        payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
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
            response.raise_for_status()
