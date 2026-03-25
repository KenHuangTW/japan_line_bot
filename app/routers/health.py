from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request

from app.config import Settings
from app.controllers.health_controller import build_healthz_response
from app.schemas.health import HealthzResponse

router = APIRouter()


def _get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


@router.get("/healthz", response_model=HealthzResponse)
async def healthz(request: Request) -> HealthzResponse:
    return build_healthz_response(_get_settings(request))
