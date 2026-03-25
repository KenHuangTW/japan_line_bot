from __future__ import annotations

from app.controllers.repositories.captured_link_repository import (
    CapturedLinkRepository,
    JsonlCapturedLinkRepository,
)

Collector = CapturedLinkRepository
JsonlCollector = JsonlCapturedLinkRepository

__all__ = ["Collector", "JsonlCollector"]
