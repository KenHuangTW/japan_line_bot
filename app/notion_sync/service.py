from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.notion_sync.models import (
    NotionDatabaseTarget,
    NotionPageResult,
    NotionSyncCandidate,
)

NOTION_API_BASE_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2026-03-11"
DEFAULT_NOTION_DATABASE_TITLE = "Nihon LINE Bot Lodgings"

TITLE_PROPERTY = "Name"
DOCUMENT_ID_PROPERTY = "Document ID"
PLATFORM_PROPERTY = "Platform"
CITY_PROPERTY = "City"
COUNTRY_CODE_PROPERTY = "Country Code"
ADDRESS_PROPERTY = "Address"
PROPERTY_TYPE_PROPERTY = "Property Type"
MAP_STATUS_PROPERTY = "Map Status"
DETAILS_STATUS_PROPERTY = "Details Status"
PRICING_STATUS_PROPERTY = "Pricing Status"
PRICE_PROPERTY = "Price"
PRICE_CURRENCY_PROPERTY = "Currency"
AVAILABILITY_PROPERTY = "Availability"
AMENITIES_PROPERTY = "Amenities"
LODGING_URL_PROPERTY = "Lodging URL"
GOOGLE_MAPS_PROPERTY = "Google Maps"
CAPTURED_AT_PROPERTY = "Captured At"

SYNC_STATUS_OPTIONS = (
    {"name": "pending", "color": "yellow"},
    {"name": "resolved", "color": "green"},
    {"name": "partial", "color": "orange"},
    {"name": "failed", "color": "red"},
    {"name": "unknown", "color": "default"},
)


class NotionApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NotionClient(Protocol):
    async def create_database(
        self,
        *,
        parent_page_id: str,
        title: str,
    ) -> NotionDatabaseTarget: ...

    async def create_page(
        self,
        *,
        data_source_id: str,
        properties: dict[str, Any],
    ) -> NotionPageResult: ...

    async def update_page(
        self,
        *,
        page_id: str,
        properties: dict[str, Any],
    ) -> NotionPageResult: ...


class HttpNotionClient:
    def __init__(
        self,
        api_token: str,
        *,
        timeout: float = 10.0,
        api_version: str = NOTION_API_VERSION,
        base_url: str = NOTION_API_BASE_URL,
    ) -> None:
        self.api_token = api_token
        self.timeout = timeout
        self.api_version = api_version
        self.base_url = base_url.rstrip("/")

    async def create_database(
        self,
        *,
        parent_page_id: str,
        title: str,
    ) -> NotionDatabaseTarget:
        payload = await self._request(
            "POST",
            "/databases",
            {
                "parent": {
                    "type": "page_id",
                    "page_id": parent_page_id,
                },
                "title": [_text_block(title)],
                "initial_data_source": {
                    "properties": build_notion_data_source_properties()
                },
            },
        )
        database_id = str(payload.get("id") or "").strip()
        if not database_id:
            raise RuntimeError("Notion create database response did not include an id.")

        target = _extract_database_target(payload)
        if target is not None:
            return target

        return await self._retrieve_database_target(database_id)

    async def create_page(
        self,
        *,
        data_source_id: str,
        properties: dict[str, Any],
    ) -> NotionPageResult:
        payload = await self._request(
            "POST",
            "/pages",
            {
                "parent": {
                    "type": "data_source_id",
                    "data_source_id": data_source_id,
                },
                "properties": properties,
            },
        )
        return _extract_page_result(payload, created=True)

    async def update_page(
        self,
        *,
        page_id: str,
        properties: dict[str, Any],
    ) -> NotionPageResult:
        payload = await self._request(
            "PATCH",
            f"/pages/{page_id}",
            {"properties": properties},
        )
        return _extract_page_result(payload, created=False)

    async def _retrieve_database_target(self, database_id: str) -> NotionDatabaseTarget:
        payload = await self._request("GET", f"/databases/{database_id}")
        target = _extract_database_target(payload)
        if target is None:
            raise RuntimeError(
                "Notion database response did not include a data source id."
            )
        return target

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Notion-Version": self.api_version,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=payload,
            )

        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        if response.is_error:
            message = body.get("message") or response.text or "Notion API request failed."
            raise NotionApiError(message, status_code=response.status_code)

        if not isinstance(body, dict):
            raise RuntimeError("Notion API returned a non-object response.")
        return body


class NotionLodgingSyncService:
    def __init__(
        self,
        client: NotionClient,
        *,
        parent_page_id: str = "",
        database_id: str = "",
        data_source_id: str = "",
        database_title: str = DEFAULT_NOTION_DATABASE_TITLE,
    ) -> None:
        self.client = client
        self.parent_page_id = parent_page_id.strip()
        self.database_id = database_id.strip()
        self.data_source_id = data_source_id.strip()
        self.database_title = database_title.strip() or DEFAULT_NOTION_DATABASE_TITLE

    @property
    def is_setup_configured(self) -> bool:
        return bool(self.parent_page_id)

    @property
    def is_sync_configured(self) -> bool:
        return bool(self.data_source_id)

    async def setup_database(self, title: str | None = None) -> NotionDatabaseTarget:
        if not self.parent_page_id:
            raise RuntimeError("NOTION_PARENT_PAGE_ID is required for Notion setup.")

        target = await self.client.create_database(
            parent_page_id=self.parent_page_id,
            title=(title or self.database_title).strip() or self.database_title,
        )
        self.configure_target(
            database_id=target.database_id,
            data_source_id=target.data_source_id,
        )
        if target.title:
            self.database_title = target.title
        return target

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult:
        if not self.data_source_id:
            raise RuntimeError("NOTION_DATA_SOURCE_ID is required for Notion sync.")

        properties = build_notion_page_properties(candidate)
        if candidate.notion_page_id:
            try:
                return await self.client.update_page(
                    page_id=candidate.notion_page_id,
                    properties=properties,
                )
            except NotionApiError as error:
                if error.status_code != 404:
                    raise

        return await self.client.create_page(
            data_source_id=self.data_source_id,
            properties=properties,
        )

    def configure_target(self, *, database_id: str, data_source_id: str) -> None:
        self.database_id = database_id.strip()
        self.data_source_id = data_source_id.strip()


def build_notion_data_source_properties() -> dict[str, Any]:
    return {
        TITLE_PROPERTY: {"title": {}},
        DOCUMENT_ID_PROPERTY: {"rich_text": {}},
        PLATFORM_PROPERTY: {
            "select": {
                "options": [
                    {"name": "booking", "color": "blue"},
                    {"name": "agoda", "color": "green"},
                    {"name": "unknown", "color": "default"},
                ]
            }
        },
        CITY_PROPERTY: {"rich_text": {}},
        COUNTRY_CODE_PROPERTY: {"rich_text": {}},
        ADDRESS_PROPERTY: {"rich_text": {}},
        PROPERTY_TYPE_PROPERTY: {"rich_text": {}},
        MAP_STATUS_PROPERTY: {"select": {"options": list(SYNC_STATUS_OPTIONS)}},
        DETAILS_STATUS_PROPERTY: {"select": {"options": list(SYNC_STATUS_OPTIONS)}},
        PRICING_STATUS_PROPERTY: {"select": {"options": list(SYNC_STATUS_OPTIONS)}},
        PRICE_PROPERTY: {"number": {"format": "number_with_commas"}},
        PRICE_CURRENCY_PROPERTY: {"rich_text": {}},
        AVAILABILITY_PROPERTY: {
            "select": {
                "options": [
                    {"name": "Available", "color": "green"},
                    {"name": "Sold Out", "color": "red"},
                    {"name": "Unknown", "color": "default"},
                ]
            }
        },
        AMENITIES_PROPERTY: {"rich_text": {}},
        LODGING_URL_PROPERTY: {"url": {}},
        GOOGLE_MAPS_PROPERTY: {"url": {}},
        CAPTURED_AT_PROPERTY: {"date": {}},
    }


def build_notion_page_properties(candidate: NotionSyncCandidate) -> dict[str, Any]:
    return {
        TITLE_PROPERTY: {"title": [_text_block(_truncate(candidate.display_name, 2000))]},
        DOCUMENT_ID_PROPERTY: {
            "rich_text": [_text_block(_truncate(str(candidate.document_id), 2000))]
        },
        PLATFORM_PROPERTY: {"select": {"name": _normalize_platform(candidate.platform)}},
        CITY_PROPERTY: {"rich_text": _rich_text_value(candidate.city)},
        COUNTRY_CODE_PROPERTY: {"rich_text": _rich_text_value(candidate.country_code)},
        ADDRESS_PROPERTY: {"rich_text": _rich_text_value(candidate.formatted_address)},
        PROPERTY_TYPE_PROPERTY: {"rich_text": _rich_text_value(candidate.property_type)},
        MAP_STATUS_PROPERTY: {"select": {"name": _normalize_status(candidate.map_status)}},
        DETAILS_STATUS_PROPERTY: {
            "select": {"name": _normalize_status(candidate.details_status)}
        },
        PRICING_STATUS_PROPERTY: {
            "select": {"name": _normalize_status(candidate.pricing_status)}
        },
        PRICE_PROPERTY: {"number": candidate.price_amount},
        PRICE_CURRENCY_PROPERTY: {"rich_text": _rich_text_value(candidate.price_currency)},
        AVAILABILITY_PROPERTY: {
            "select": {"name": _availability_name(candidate.is_sold_out)}
        },
        AMENITIES_PROPERTY: {
            "rich_text": _rich_text_value(", ".join(candidate.amenities))
        },
        LODGING_URL_PROPERTY: {"url": _safe_url(candidate.target_url)},
        GOOGLE_MAPS_PROPERTY: {"url": _safe_url(candidate.maps_url)},
        CAPTURED_AT_PROPERTY: {
            "date": (
                {"start": candidate.captured_at.isoformat()}
                if candidate.captured_at is not None
                else None
            )
        },
    }


def _extract_database_target(payload: dict[str, Any]) -> NotionDatabaseTarget | None:
    database_id = str(payload.get("id") or "").strip()
    if not database_id:
        return None

    data_sources = payload.get("data_sources") or []
    if not data_sources and isinstance(payload.get("initial_data_source"), dict):
        data_sources = [payload["initial_data_source"]]

    if not data_sources:
        return None

    first_source = data_sources[0]
    data_source_id = str(first_source.get("id") or "").strip()
    if not data_source_id:
        return None

    return NotionDatabaseTarget(
        database_id=database_id,
        data_source_id=data_source_id,
        title=_extract_plain_text(payload.get("title")),
    )


def _extract_page_result(
    payload: dict[str, Any],
    *,
    created: bool,
) -> NotionPageResult:
    page_id = str(payload.get("id") or "").strip()
    if not page_id:
        raise RuntimeError("Notion page response did not include an id.")

    page_url = payload.get("url")
    return NotionPageResult(
        page_id=page_id,
        page_url=page_url if isinstance(page_url, str) and page_url else None,
        created=created,
    )


def _extract_plain_text(value: Any) -> str | None:
    if not isinstance(value, list):
        return None

    texts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        plain_text = item.get("plain_text")
        if isinstance(plain_text, str) and plain_text:
            texts.append(plain_text)
            continue

        text_object = item.get("text")
        if isinstance(text_object, dict):
            content = text_object.get("content")
            if isinstance(content, str) and content:
                texts.append(content)

    if not texts:
        return None
    return "".join(texts)


def _rich_text_value(value: str | None) -> list[dict[str, Any]]:
    text = _truncate((value or "").strip(), 2000)
    if not text:
        return []
    return [_text_block(text)]


def _text_block(text: str) -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": text},
    }


def _truncate(value: str, limit: int) -> str:
    return value[:limit]


def _normalize_platform(platform: str | None) -> str:
    text = (platform or "").strip().lower()
    if text in {"booking", "agoda"}:
        return text
    return "unknown"


def _normalize_status(status: str | None) -> str:
    text = (status or "").strip().lower()
    if text in {"pending", "resolved", "partial", "failed"}:
        return text
    return "unknown"


def _availability_name(is_sold_out: bool | None) -> str:
    if is_sold_out is True:
        return "Sold Out"
    if is_sold_out is False:
        return "Available"
    return "Unknown"


def _safe_url(url: str | None) -> str | None:
    text = (url or "").strip()
    if not text:
        return None
    if len(text) > 2000:
        return None
    return text
