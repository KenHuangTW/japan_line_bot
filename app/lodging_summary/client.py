from __future__ import annotations

import asyncio
import json
from json import JSONDecodeError
from typing import Any

import httpx
from pydantic import ValidationError

from app.lodging_summary.errors import (
    LodgingDecisionSummaryInvalidResponseError,
    LodgingDecisionSummaryProviderError,
    LodgingDecisionSummaryTimeoutError,
)
from app.schemas.lodging_summary import (
    LODGING_DECISION_SUMMARY_RESPONSE_JSON_SCHEMA,
    LodgingDecisionSummaryRequest,
    LodgingDecisionSummaryResponse,
)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
RETRYABLE_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}

SUMMARY_PROMPT = """
你是旅遊住宿決策助理。請只根據提供的 JSON 住宿資料產生摘要，並遵守以下規則：

1. 使用繁體中文。
2. 不可捏造不存在的價格、地點、設備或評價。
3. top_candidates 只列最值得優先討論的 1 到 3 個候選，且 document_id 必須直接引用輸入中的 lodging document_id。
4. pros / cons / missing_information / discussion_points 各自保持精簡，最多 5 項。
5. 若資料不足，請把不確定內容放進 missing_information，而不是自行猜測。
6. 請優先比較價格、可訂狀態、地點資訊、設備完整度與最新更新時間。
""".strip()


class GeminiDecisionSummaryClient:
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

    async def generate_summary(
        self,
        request: LodgingDecisionSummaryRequest,
    ) -> LodgingDecisionSummaryResponse:
        payload = _build_gemini_payload(request)
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await self._post_with_retries(client, payload)
        except httpx.TimeoutException as exc:
            raise LodgingDecisionSummaryTimeoutError(
                "Gemini summary request timed out."
            ) from exc
        except httpx.HTTPStatusError as exc:
            response_text = _truncate_response_text(exc.response.text)
            raise LodgingDecisionSummaryProviderError(
                "Gemini summary request failed "
                f"with status {exc.response.status_code}: {response_text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LodgingDecisionSummaryProviderError(
                "Gemini summary request failed."
            ) from exc

        return _parse_gemini_response(response.json())

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

        raise LodgingDecisionSummaryProviderError(
            "Gemini summary request exhausted retries."
        )

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))


def _build_gemini_payload(
    request: LodgingDecisionSummaryRequest,
) -> dict[str, Any]:
    request_json = json.dumps(
        request.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        indent=2,
    )
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"{SUMMARY_PROMPT}\n\n"
                            "住宿資料如下，請直接根據此 JSON 產生結構化摘要：\n"
                            f"{request_json}"
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseJsonSchema": LODGING_DECISION_SUMMARY_RESPONSE_JSON_SCHEMA,
        },
    }


def _parse_gemini_response(payload: dict[str, Any]) -> LodgingDecisionSummaryResponse:
    response_text = _extract_response_text(payload)
    try:
        parsed = json.loads(response_text)
    except JSONDecodeError as exc:
        raise LodgingDecisionSummaryInvalidResponseError(
            "Gemini summary response was not valid JSON."
        ) from exc

    try:
        return LodgingDecisionSummaryResponse.model_validate(parsed)
    except ValidationError as exc:
        raise LodgingDecisionSummaryInvalidResponseError(
            "Gemini summary response did not match the expected schema."
        ) from exc


def _extract_response_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise LodgingDecisionSummaryInvalidResponseError(
            "Gemini summary response did not contain candidates."
        )

    content = candidates[0].get("content")
    if not isinstance(content, dict):
        raise LodgingDecisionSummaryInvalidResponseError(
            "Gemini summary response did not contain content."
        )

    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise LodgingDecisionSummaryInvalidResponseError(
            "Gemini summary response did not contain content parts."
        )

    text = parts[0].get("text")
    if not isinstance(text, str) or not text.strip():
        raise LodgingDecisionSummaryInvalidResponseError(
            "Gemini summary response did not contain text output."
        )
    return text


def _truncate_response_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        return "empty response body"
    if len(normalized) <= 300:
        return normalized
    return f"{normalized[:299].rstrip()}…"
