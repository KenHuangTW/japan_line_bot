from __future__ import annotations

from pydantic import BaseModel


class HealthzResponse(BaseModel):
    status: str
    environment: str
    line_secret_configured: bool
    line_reply_configured: bool
    storage_backend: str
    storage_target: str
