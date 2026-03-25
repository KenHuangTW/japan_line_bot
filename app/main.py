from __future__ import annotations

from fastapi import FastAPI

from app.collector import Collector, JsonlCollector
from app.config import Settings
from app.line_client import HttpLineClient, LineClient, NoopLineClient
from app.routers import health_router, line_webhook_router


def create_app(
    settings: Settings | None = None,
    collector: Collector | None = None,
    line_client: LineClient | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    active_collector = collector or JsonlCollector(
        active_settings.collector_output_path
    )
    active_line_client = line_client or (
        HttpLineClient(active_settings.line_channel_access_token)
        if active_settings.line_channel_access_token
        else NoopLineClient()
    )

    app = FastAPI(
        title="Nihon Line Bot",
        version="0.1.0",
    )
    app.state.settings = active_settings
    app.state.collector = active_collector
    app.state.captured_link_repository = active_collector
    app.state.line_client = active_line_client

    app.include_router(health_router)
    app.include_router(line_webhook_router)

    return app


app = create_app()
