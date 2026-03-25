from __future__ import annotations

import json

from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings
from app.controllers.validators.line_security import verify_signature
from app.schemas.line_webhook import LineWebhookRequest


def ensure_line_webhook_request_is_valid(
    settings: Settings,
    body: bytes,
    signature: str | None,
) -> None:
    if not settings.is_line_secret_configured:
        raise HTTPException(
            status_code=503,
            detail="LINE channel secret is not configured.",
        )

    if not verify_signature(
        settings.line_channel_secret,
        body,
        signature,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid LINE signature.",
        )


def parse_line_webhook_payload(body: bytes) -> LineWebhookRequest:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload.",
        ) from exc

    try:
        return LineWebhookRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid LINE webhook payload.",
        ) from exc
