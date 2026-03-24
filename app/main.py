from __future__ import annotations

import json

from fastapi import FastAPI, Header, HTTPException, Request

from app.collector import Collector, JsonlCollector
from app.config import Settings
from app.line_client import HttpLineClient, LineClient, NoopLineClient
from app.line_security import verify_signature
from app.line_service import process_events


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
    app.state.line_client = active_line_client

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "environment": active_settings.app_env,
            "line_secret_configured": active_settings.is_line_secret_configured,
            "line_reply_configured": active_settings.is_line_reply_configured,
            "collector_output_path": str(
                active_settings.collector_output_path
            ),
        }

    @app.post("/webhooks/line")
    async def line_webhook(
        request: Request,
        x_line_signature: str | None = Header(
            default=None,
            alias="X-Line-Signature",
        ),
    ) -> dict[str, object]:
        if not active_settings.is_line_secret_configured:
            raise HTTPException(
                status_code=503,
                detail="LINE channel secret is not configured.",
            )

        body = await request.body()
        if not verify_signature(
            active_settings.line_channel_secret,
            body,
            x_line_signature,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid LINE signature.",
            )

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON payload.",
            ) from exc

        captured = await process_events(
            payload=payload,
            settings=active_settings,
            collector=active_collector,
            line_client=active_line_client,
        )
        return {
            "ok": True,
            "captured": captured,
        }

    return app


app = create_app()
