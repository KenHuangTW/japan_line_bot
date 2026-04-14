from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.notion_sync.service import (
    DEFAULT_NOTION_DATABASE_TITLE,
    NOTION_API_VERSION,
)


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return (
        tuple(item.strip().lower() for item in raw_value.split(",") if item.strip())
        or default
    )


def _redact_uri_password(uri: str) -> str:
    parts = urlsplit(uri)
    if not parts.password:
        return uri.rstrip("/")

    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    netloc = f"{parts.username}:***@{host}" if parts.username else host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"

    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            parts.query,
            parts.fragment,
        )
    ).rstrip("/")


class Settings(BaseModel):
    app_env: str = "development"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_database: str = "nihon_line_bot"
    mongo_collection: str = "captured_lodging_links"
    trip_collection: str = "line_trips"
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_reply_on_capture: bool = True
    line_welcome_message: str = (
        "已加入群組。請先用 /建立旅次 <名稱> 建立目前旅次，再貼 Booking、Agoda 或 Airbnb 的住宿連結。"
    )
    reply_capture_template: str = "已收到 {count} 筆住宿連結，會自動整理並同步到 Notion。"
    reply_duplicate_link_template: str = "你是不是在找這個\n{url}"
    supported_domains: tuple[str, ...] = Field(
        default=("booking.com", "agoda.com", "airbnb.com", "airbnb.com.tw")
    )
    map_enrichment_batch_size: int = 20
    map_enrichment_request_timeout: float = 10.0
    map_enrichment_max_retry_count: int = 3
    notion_api_token: str = ""
    notion_parent_page_id: str = ""
    notion_database_id: str = ""
    notion_data_source_id: str = ""
    notion_database_title: str = DEFAULT_NOTION_DATABASE_TITLE
    notion_database_url: str = ""
    notion_public_database_url: str = ""
    notion_target_collection: str = "notion_targets"
    notion_api_version: str = NOTION_API_VERSION
    notion_request_timeout: float = 10.0
    notion_sync_batch_size: int = 20

    @property
    def is_line_secret_configured(self) -> bool:
        return bool(self.line_channel_secret.strip())

    @property
    def is_line_reply_configured(self) -> bool:
        return self.is_line_secret_configured and bool(
            self.line_channel_access_token.strip()
        )

    @property
    def storage_target(self) -> str:
        return (
            f"{_redact_uri_password(self.mongo_uri)}/"
            f"{self.mongo_database}.{self.mongo_collection}"
        )

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            mongo_uri=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"),
            mongo_database=os.getenv("MONGO_DATABASE", "nihon_line_bot"),
            mongo_collection=os.getenv(
                "MONGO_COLLECTION", "captured_lodging_links"
            ),
            trip_collection=os.getenv("TRIP_COLLECTION", "line_trips"),
            line_channel_secret=os.getenv("LINE_CHANNEL_SECRET", ""),
            line_channel_access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""),
            line_reply_on_capture=_env_bool("LINE_REPLY_ON_CAPTURE", True),
            line_welcome_message=os.getenv(
                "LINE_WELCOME_MESSAGE",
                "已加入群組。請先用 /建立旅次 <名稱> 建立目前旅次，再貼 Booking、Agoda 或 Airbnb 的住宿連結。",
            ),
            reply_capture_template=os.getenv(
                "REPLY_CAPTURE_TEMPLATE",
                "已收到 {count} 筆住宿連結，會自動整理並同步到 Notion。",
            ),
            reply_duplicate_link_template=os.getenv(
                "REPLY_DUPLICATE_LINK_TEMPLATE",
                "你是不是在找這個\n{url}",
            ),
            supported_domains=_env_csv(
                "SUPPORTED_DOMAINS",
                ("booking.com", "agoda.com", "airbnb.com", "airbnb.com.tw"),
            ),
            map_enrichment_batch_size=int(
                os.getenv("MAP_ENRICHMENT_BATCH_SIZE", "20")
            ),
            map_enrichment_request_timeout=float(
                os.getenv("MAP_ENRICHMENT_REQUEST_TIMEOUT", "10.0")
            ),
            map_enrichment_max_retry_count=int(
                os.getenv("MAP_ENRICHMENT_MAX_RETRY_COUNT", "3")
            ),
            notion_api_token=os.getenv("NOTION_API_TOKEN", ""),
            notion_parent_page_id=os.getenv("NOTION_PARENT_PAGE_ID", ""),
            notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
            notion_data_source_id=os.getenv("NOTION_DATA_SOURCE_ID", ""),
            notion_database_title=os.getenv(
                "NOTION_DATABASE_TITLE", DEFAULT_NOTION_DATABASE_TITLE
            ),
            notion_database_url=os.getenv("NOTION_DATABASE_URL", ""),
            notion_public_database_url=os.getenv(
                "NOTION_PUBLIC_DATABASE_URL", ""
            ),
            notion_target_collection=os.getenv(
                "NOTION_TARGET_COLLECTION", "notion_targets"
            ),
            notion_api_version=os.getenv("NOTION_API_VERSION", NOTION_API_VERSION),
            notion_request_timeout=float(
                os.getenv("NOTION_REQUEST_TIMEOUT", "10.0")
            ),
            notion_sync_batch_size=int(os.getenv("NOTION_SYNC_BATCH_SIZE", "20")),
        )
