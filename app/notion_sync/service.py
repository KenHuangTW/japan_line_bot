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

TITLE_PROPERTY = "名稱"
PLATFORM_PROPERTY = "平台"
LODGING_URL_PROPERTY = "房源URL"
GOOGLE_MAPS_PROPERTY = "Google 地圖 URL"
AMENITIES_PROPERTY = "設施"
LAST_UPDATED_PROPERTY = "最後更新時間"
DOCUMENT_ID_PROPERTY = "ID"

PLATFORM_OPTIONS = [
    {"name": "booking", "color": "blue"},
    {"name": "agoda", "color": "green"},
    {"name": "unknown", "color": "default"},
]

PROPERTY_SPECS = (
    {
        "key": "title",
        "label": TITLE_PROPERTY,
        "aliases": (TITLE_PROPERTY, "Name"),
        "definition": {"title": {}},
    },
    {
        "key": "platform",
        "label": PLATFORM_PROPERTY,
        "aliases": (PLATFORM_PROPERTY, "Platform"),
        "definition": {"select": {"options": list(PLATFORM_OPTIONS)}},
    },
    {
        "key": "lodging_url",
        "label": LODGING_URL_PROPERTY,
        "aliases": (LODGING_URL_PROPERTY, "Lodging URL"),
        "definition": {"url": {}},
    },
    {
        "key": "google_maps_url",
        "label": GOOGLE_MAPS_PROPERTY,
        "aliases": (GOOGLE_MAPS_PROPERTY, "Google Maps"),
        "definition": {"url": {}},
    },
    {
        "key": "amenities",
        "label": AMENITIES_PROPERTY,
        "aliases": (AMENITIES_PROPERTY, "Amenities"),
        "definition": {"rich_text": {}},
    },
    {
        "key": "last_updated_at",
        "label": LAST_UPDATED_PROPERTY,
        "aliases": (LAST_UPDATED_PROPERTY, "Captured At"),
        "definition": {"date": {}},
    },
    {
        "key": "document_id",
        "label": DOCUMENT_ID_PROPERTY,
        "aliases": (DOCUMENT_ID_PROPERTY, "Document ID"),
        "definition": {"rich_text": {}},
    },
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

    async def retrieve_database(
        self,
        *,
        database_id: str,
    ) -> dict[str, Any]: ...

    async def retrieve_data_source(
        self,
        *,
        data_source_id: str,
    ) -> dict[str, Any]: ...

    async def update_data_source(
        self,
        *,
        data_source_id: str,
        title: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def retrieve_page(
        self,
        *,
        page_id: str,
    ) -> dict[str, Any]: ...

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

    async def retrieve_database(
        self,
        *,
        database_id: str,
    ) -> dict[str, Any]:
        return await self._request("GET", f"/databases/{database_id}")

    async def retrieve_data_source(
        self,
        *,
        data_source_id: str,
    ) -> dict[str, Any]:
        return await self._request("GET", f"/data_sources/{data_source_id}")

    async def update_data_source(
        self,
        *,
        data_source_id: str,
        title: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PATCH",
            f"/data_sources/{data_source_id}",
            {
                "title": [_text_block(title)],
                "properties": properties,
            },
        )

    async def retrieve_page(
        self,
        *,
        page_id: str,
    ) -> dict[str, Any]:
        return await self._request("GET", f"/pages/{page_id}")

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
        payload = await self.retrieve_database(database_id=database_id)
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
        database_url: str = "",
        public_database_url: str = "",
    ) -> None:
        self.client = client
        self.parent_page_id = parent_page_id.strip()
        self.database_id = database_id.strip()
        self.data_source_id = data_source_id.strip()
        self.database_title = database_title.strip() or DEFAULT_NOTION_DATABASE_TITLE
        self.database_url = database_url.strip()
        self.public_database_url = public_database_url.strip()

    @property
    def is_setup_configured(self) -> bool:
        return bool(self.parent_page_id or self.data_source_id)

    @property
    def is_sync_configured(self) -> bool:
        return bool(self.data_source_id)

    async def setup_database(self, title: str | None = None) -> NotionDatabaseTarget:
        target_title = (title or self.database_title).strip() or self.database_title
        if self.data_source_id:
            data_source = await self.client.retrieve_data_source(
                data_source_id=self.data_source_id,
            )
            updated_data_source = await self.client.update_data_source(
                data_source_id=self.data_source_id,
                title=target_title,
                properties=build_notion_data_source_update_properties(data_source),
            )
            self.configure_target(
                database_id=_extract_parent_database_id(updated_data_source)
                or _extract_parent_database_id(data_source)
                or self.database_id,
                data_source_id=str(updated_data_source.get("id") or self.data_source_id),
            )
            self.database_title = (
                _extract_plain_text(updated_data_source.get("title")) or target_title
            )
            target = await self.refresh_database_target()
            if target is not None:
                return target
            return NotionDatabaseTarget(
                database_id=self.database_id,
                data_source_id=self.data_source_id,
                title=self.database_title,
                url=self.database_url or None,
                public_url=self.public_database_url or None,
            )

        if not self.parent_page_id:
            raise RuntimeError("NOTION_PARENT_PAGE_ID is required for Notion setup.")

        target = await self.client.create_database(
            parent_page_id=self.parent_page_id,
            title=target_title,
        )
        self.configure_target(
            database_id=target.database_id,
            data_source_id=target.data_source_id,
            database_url=target.url,
            public_database_url=target.public_url,
        )
        if target.title:
            self.database_title = target.title
        return NotionDatabaseTarget(
            database_id=self.database_id,
            data_source_id=self.data_source_id,
            title=self.database_title,
            url=self.database_url or None,
            public_url=self.public_database_url or None,
        )

    async def get_database_url(self, *, prefer_public: bool = True) -> str | None:
        if prefer_public and self.public_database_url:
            return self.public_database_url
        if not prefer_public and self.database_url:
            return self.database_url
        if self.database_id:
            target = await self.refresh_database_target()
            if target is not None:
                if prefer_public and target.public_url:
                    return target.public_url
                if target.url:
                    return target.url
                if not prefer_public and target.public_url:
                    return target.public_url
        return self.public_database_url or self.database_url or None

    async def refresh_database_target(self) -> NotionDatabaseTarget | None:
        if not self.database_id:
            return None
        payload = await self.client.retrieve_database(database_id=self.database_id)
        target = _extract_database_target(payload)
        if target is None:
            return None
        self.configure_target(
            database_id=target.database_id,
            data_source_id=self.data_source_id or target.data_source_id,
            database_url=target.url,
            public_database_url=target.public_url,
        )
        if target.title:
            self.database_title = target.title
        return NotionDatabaseTarget(
            database_id=self.database_id,
            data_source_id=self.data_source_id,
            title=self.database_title,
            url=self.database_url or None,
            public_url=self.public_database_url or None,
        )

    async def sync_document(self, candidate: NotionSyncCandidate) -> NotionPageResult:
        if not self.data_source_id:
            raise RuntimeError("NOTION_DATA_SOURCE_ID is required for Notion sync.")

        properties = build_notion_page_properties(candidate)
        if await self._should_update_existing_page(candidate):
            try:
                return await self.client.update_page(
                    page_id=str(candidate.notion_page_id),
                    properties=properties,
                )
            except NotionApiError as error:
                if error.status_code != 404 and not _is_archived_block_error(error):
                    raise

        return await self.client.create_page(
            data_source_id=self.data_source_id,
            properties=properties,
        )

    def configure_target(
        self,
        *,
        database_id: str,
        data_source_id: str,
        database_url: str | None = None,
        public_database_url: str | None = None,
    ) -> None:
        self.database_id = database_id.strip()
        self.data_source_id = data_source_id.strip()
        if database_url is not None:
            self.database_url = database_url.strip()
        if public_database_url is not None:
            self.public_database_url = public_database_url.strip()

    async def _should_update_existing_page(
        self,
        candidate: NotionSyncCandidate,
    ) -> bool:
        if not candidate.notion_page_id:
            return False

        if candidate.notion_data_source_id:
            return candidate.notion_data_source_id == self.data_source_id

        if candidate.notion_database_id and self.database_id:
            return candidate.notion_database_id == self.database_id

        try:
            page = await self.client.retrieve_page(page_id=str(candidate.notion_page_id))
        except NotionApiError as error:
            if error.status_code == 404:
                return False
            raise

        if _is_archived_page(page):
            return False

        page_data_source_id = _extract_parent_data_source_id(page)
        if page_data_source_id:
            return page_data_source_id == self.data_source_id

        page_database_id = _extract_parent_database_id(page)
        if page_database_id and self.database_id:
            return page_database_id == self.database_id

        return True


def build_notion_data_source_properties() -> dict[str, Any]:
    return {
        str(spec["label"]): dict(spec["definition"])
        for spec in PROPERTY_SPECS
    }


def build_notion_data_source_update_properties(
    data_source: dict[str, Any],
) -> dict[str, Any]:
    properties = data_source.get("properties")
    if not isinstance(properties, dict):
        return build_notion_data_source_properties()

    updates: dict[str, Any] = {}
    matched_keys: set[str] = set()
    for property_name, config in properties.items():
        if not isinstance(config, dict):
            continue

        spec = _match_property_spec(property_name)
        property_id = str(config.get("id") or property_name)
        if spec is None:
            updates[property_id] = None
            continue

        matched_keys.add(str(spec["key"]))
        updates[property_id] = {
            "name": spec["label"],
            **dict(spec["definition"]),
        }

    for spec in PROPERTY_SPECS:
        if str(spec["key"]) in matched_keys:
            continue
        updates[str(spec["label"])] = dict(spec["definition"])

    return updates


def build_notion_page_properties(candidate: NotionSyncCandidate) -> dict[str, Any]:
    last_updated_at = candidate.last_updated_at or candidate.captured_at
    return {
        TITLE_PROPERTY: {"title": [_text_block(_truncate(candidate.display_name, 2000))]},
        PLATFORM_PROPERTY: {"select": {"name": _normalize_platform(candidate.platform)}},
        LODGING_URL_PROPERTY: {"url": _safe_url(candidate.target_url)},
        GOOGLE_MAPS_PROPERTY: {"url": _safe_url(candidate.maps_url)},
        AMENITIES_PROPERTY: {"rich_text": _rich_text_value(", ".join(candidate.amenities))},
        LAST_UPDATED_PROPERTY: {
            "date": (
                {"start": last_updated_at.isoformat()}
                if last_updated_at is not None
                else None
            )
        },
        DOCUMENT_ID_PROPERTY: {
            "rich_text": [_text_block(_truncate(str(candidate.document_id), 2000))]
        },
    }


def _match_property_spec(property_name: str) -> dict[str, Any] | None:
    normalized_name = property_name.strip()
    for spec in PROPERTY_SPECS:
        aliases = spec.get("aliases") or ()
        if normalized_name in aliases:
            return spec
    return None


def _extract_parent_database_id(payload: dict[str, Any]) -> str | None:
    parent = payload.get("parent")
    if not isinstance(parent, dict):
        return None
    database_id = parent.get("database_id")
    if isinstance(database_id, str) and database_id.strip():
        return database_id.strip()
    return None


def _extract_parent_data_source_id(payload: dict[str, Any]) -> str | None:
    parent = payload.get("parent")
    if not isinstance(parent, dict):
        return None
    data_source_id = parent.get("data_source_id")
    if isinstance(data_source_id, str) and data_source_id.strip():
        return data_source_id.strip()
    return None


def _is_archived_page(payload: dict[str, Any]) -> bool:
    return bool(payload.get("archived")) or bool(payload.get("in_trash"))


def _is_archived_block_error(error: NotionApiError) -> bool:
    return "archived" in str(error).lower()


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
        url=_extract_url(payload.get("url")),
        public_url=_extract_url(payload.get("public_url")),
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


def _extract_url(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


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


def _safe_url(url: str | None) -> str | None:
    text = (url or "").strip()
    if not text:
        return None
    if len(text) > 2000:
        return None
    return text
