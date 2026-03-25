from __future__ import annotations

from app.config import Settings
from app.schemas.health import HealthzResponse


def build_healthz_response(settings: Settings) -> HealthzResponse:
    return HealthzResponse(
        status="ok",
        environment=settings.app_env,
        line_secret_configured=settings.is_line_secret_configured,
        line_reply_configured=settings.is_line_reply_configured,
        storage_backend=settings.storage_backend,
        storage_target=settings.storage_target,
    )
