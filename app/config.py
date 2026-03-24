from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return tuple(
        item.strip().lower()
        for item in raw_value.split(",")
        if item.strip()
    ) or default


class Settings(BaseModel):
    app_env: str = "development"
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_reply_on_capture: bool = True
    line_welcome_message: str = (
        "已加入群組。之後只要貼 Booking 或 Agoda 的住宿連結，我就會先幫你收下來。"
    )
    reply_capture_template: str = "已收到 {count} 筆住宿連結，先幫你記下來了。"
    supported_domains: tuple[str, ...] = Field(
        default=("booking.com", "agoda.com")
    )
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

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
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
