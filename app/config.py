from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from pydantic import BaseModel, Field

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
    line_command_control_source_group_id: str = ""
    line_command_control_target_group_id: str = ""
    line_reply_on_capture: bool = True
    line_welcome_message: str = (
        "已加入群組。請先用 /建立旅次 <名稱> 建立目前旅次，再貼 Booking、Agoda 或 Airbnb 的住宿連結。"
    )
    reply_capture_template: str = "已收到 {count} 筆住宿連結，會整理到目前旅次。"
    reply_duplicate_link_template: str = "你是不是在找這個\n{url}"
    supported_domains: tuple[str, ...] = Field(
        default=("booking.com", "agoda.com", "airbnb.com", "airbnb.com.tw")
    )
    map_enrichment_batch_size: int = 20
    map_enrichment_request_timeout: float = 10.0
    map_enrichment_max_retry_count: int = 3
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_request_timeout: float = 15.0

    @property
    def is_line_secret_configured(self) -> bool:
        return bool(self.line_channel_secret.strip())

    @property
    def is_line_reply_configured(self) -> bool:
        return self.is_line_secret_configured and bool(
            self.line_channel_access_token.strip()
        )

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @property
    def has_line_command_group_override(self) -> bool:
        return bool(
            self.line_command_control_source_group_id.strip()
            and self.line_command_control_target_group_id.strip()
        )

    def resolve_line_target_source(
        self,
        *,
        source_type: str,
        group_id: str | None,
        room_id: str | None,
        user_id: str | None,
    ) -> tuple[str, str | None, str | None, str | None]:
        if not self.has_line_command_group_override:
            return source_type, group_id, room_id, user_id

        control_group_id = self.line_command_control_source_group_id.strip()
        target_group_id = self.line_command_control_target_group_id.strip()
        if source_type != "group" or group_id != control_group_id:
            return source_type, group_id, room_id, user_id

        return "group", target_group_id, None, user_id

    def resolve_line_command_source(
        self,
        *,
        source_type: str,
        group_id: str | None,
        room_id: str | None,
        user_id: str | None,
    ) -> tuple[str, str | None, str | None, str | None]:
        return self.resolve_line_target_source(
            source_type=source_type,
            group_id=group_id,
            room_id=room_id,
            user_id=user_id,
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
            line_command_control_source_group_id=os.getenv(
                "LINE_COMMAND_CONTROL_SOURCE_GROUP_ID", ""
            ),
            line_command_control_target_group_id=os.getenv(
                "LINE_COMMAND_CONTROL_TARGET_GROUP_ID", ""
            ),
            line_reply_on_capture=_env_bool("LINE_REPLY_ON_CAPTURE", True),
            line_welcome_message=os.getenv(
                "LINE_WELCOME_MESSAGE",
                "已加入群組。請先用 /建立旅次 <名稱> 建立目前旅次，再貼 Booking、Agoda 或 Airbnb 的住宿連結。",
            ),
            reply_capture_template=os.getenv(
                "REPLY_CAPTURE_TEMPLATE",
                "已收到 {count} 筆住宿連結，會整理到目前旅次。",
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
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_request_timeout=float(
                os.getenv("GEMINI_REQUEST_TIMEOUT", "15.0")
            ),
        )
