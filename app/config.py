from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
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
    storage_backend: Literal["mongo", "jsonl"] = "mongo"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_database: str = "nihon_line_bot"
    mongo_collection: str = "captured_lodging_links"
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_reply_on_capture: bool = True
    line_welcome_message: str = (
        "已加入群組。之後只要貼 Booking 或 Agoda 的住宿連結，我就會先幫你收下來。"
    )
    reply_capture_template: str = "已收到 {count} 筆住宿連結，先幫你記下來了。"
    supported_domains: tuple[str, ...] = Field(default=("booking.com", "agoda.com"))
    collector_output_path: Path = Field(
        default=Path("data/captured_lodging_links.jsonl")
    )

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
        if self.storage_backend == "mongo":
            return (
                f"{_redact_uri_password(self.mongo_uri)}/"
                f"{self.mongo_database}.{self.mongo_collection}"
            )
        return str(self.collector_output_path)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            storage_backend=os.getenv("STORAGE_BACKEND", "mongo"),
            mongo_uri=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"),
            mongo_database=os.getenv("MONGO_DATABASE", "nihon_line_bot"),
            mongo_collection=os.getenv(
                "MONGO_COLLECTION", "captured_lodging_links"
            ),
            line_channel_secret=os.getenv("LINE_CHANNEL_SECRET", ""),
            line_channel_access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""),
            line_reply_on_capture=_env_bool("LINE_REPLY_ON_CAPTURE", True),
            line_welcome_message=os.getenv(
                "LINE_WELCOME_MESSAGE",
                "已加入群組。之後只要貼 Booking 或 Agoda 的住宿連結，我就會先幫你收下來。",
            ),
            reply_capture_template=os.getenv(
                "REPLY_CAPTURE_TEMPLATE",
                "已收到 {count} 筆住宿連結，先幫你記下來了。",
            ),
            supported_domains=_env_csv(
                "SUPPORTED_DOMAINS", ("booking.com", "agoda.com")
            ),
            collector_output_path=Path(
                os.getenv(
                    "COLLECTOR_OUTPUT_PATH",
                    "data/captured_lodging_links.jsonl",
                )
            ),
        )
