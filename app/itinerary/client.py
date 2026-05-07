from __future__ import annotations

import asyncio
import json
import logging
from json import JSONDecodeError
from typing import Any

import httpx
from pydantic import ValidationError

from app.itinerary.parser import ParsedItinerary
from app.itinerary.service import (
    DeterministicItineraryProvider,
    ItineraryImportError,
    ItineraryNormalizationResult,
)
from app.models import ItineraryDayNote, ItineraryItemPayload

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
RETRYABLE_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)

ITINERARY_PROMPT = """
你是旅遊行程整理助理。請只根據提供的 JSON rows / day_notes 整理行程，不可新增不存在的行程。

規則：
1. 使用繁體中文。
2. 保留每一筆 row，不可刪除或合併。
3. item_type 只能使用 attraction、food、shopping、transport、lodging、free_time、note、other。
4. status 只能使用 confirmed、tentative、optional。
5. 有「可選」語意的項目標成 optional；自由或待確認語意標成 tentative。
6. location_name 若是交通移動或自由時間可以為 null；其他行程優先使用 title 作為地點名稱。
""".strip()


class GeminiItineraryProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        timeout: float = 15.0,
        base_url: str = GEMINI_API_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.fallback_provider = DeterministicItineraryProvider()

    async def normalize(
        self,
        parsed: ParsedItinerary,
        *,
        timezone_name: str,
    ) -> ItineraryNormalizationResult:
        if not parsed.rows and not parsed.day_notes:
            return ItineraryNormalizationResult(items=(), day_notes=())

        payload = _build_gemini_payload(parsed, timezone_name=timezone_name)
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await self._post_with_retries(client, payload)
            result = _parse_response(response.json())
        except Exception as exc:
            logger.warning(
                "Gemini itinerary normalization failed; falling back to deterministic parser.",
                exc_info=exc,
            )
            return await self.fallback_provider.normalize(
                parsed,
                timezone_name=timezone_name,
            )

        if parsed.rows and not result.items:
            logger.warning(
                "Gemini itinerary normalization returned no items; falling back to deterministic parser."
            )
            return await self.fallback_provider.normalize(
                parsed,
                timezone_name=timezone_name,
            )
        return result

    async def _post_with_retries(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(
                    f"/v1beta/models/{self.model}:generateContent",
                    headers={
                        "x-goog-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                raise
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if (
                    exc.response.status_code in RETRYABLE_GEMINI_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    await self._sleep_before_retry(attempt)
                    continue
                raise
            return response
        raise ItineraryImportError("Gemini itinerary request exhausted retries.")

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))


def _build_gemini_payload(
    parsed: ParsedItinerary,
    *,
    timezone_name: str,
) -> dict[str, Any]:
    request = {
        "timezone": timezone_name,
        "rows": [
            {
                "day_index": row.day_index,
                "date": row.date.isoformat(),
                "start_time": row.start_time.isoformat(timespec="minutes")
                if row.start_time
                else None,
                "end_time": row.end_time.isoformat(timespec="minutes")
                if row.end_time
                else None,
                "title": row.title,
                "description": row.description,
                "source_line_hash": row.source_line_hash,
            }
            for row in parsed.rows
        ],
        "day_notes": [
            {
                "day_index": note.day_index,
                "date": note.date.isoformat() if note.date else None,
                "title": note.title,
                "content": note.content,
            }
            for note in parsed.day_notes
        ],
    }
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"{ITINERARY_PROMPT}\n\n"
                            "請輸出 JSON：{items: [...], day_notes: [...]}。\n"
                            f"{json.dumps(request, ensure_ascii=False, indent=2)}"
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }


def _parse_response(payload: dict[str, Any]) -> ItineraryNormalizationResult:
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        items = tuple(
            ItineraryItemPayload.model_validate(item)
            for item in parsed.get("items", [])
        )
        day_notes = tuple(
            ItineraryDayNote.model_validate(
                {
                    "trip_id": "",
                    **note,
                }
            )
            for note in parsed.get("day_notes", [])
        )
    except (KeyError, IndexError, TypeError, JSONDecodeError, ValidationError) as exc:
        raise ItineraryImportError(
            "Gemini itinerary response did not match the expected schema."
        ) from exc
    return ItineraryNormalizationResult(items=items, day_notes=day_notes)
