from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Header, Request

from app.config import Settings
from app.controllers.integration.line_client import LineClient
from app.controllers.line_webhook_controller import process_events
from app.controllers.repositories.captured_link_repository import (
    CapturedLinkRepository,
)
from app.lodging_links import LodgingLinkService
from app.map_enrichment import LodgingMapEnrichmentService, MapEnrichmentRepository
from app.notion_sync import NotionLodgingSyncService, NotionSyncRepository
from app.controllers.validators.line_webhook import (
    ensure_line_webhook_request_is_valid,
    parse_line_webhook_payload,
)
from app.schemas.line_webhook import LineWebhookResponse

router = APIRouter()


def _get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _get_captured_link_repository(
    request: Request,
) -> CapturedLinkRepository:
    return cast(
        CapturedLinkRepository,
        request.app.state.captured_link_repository,
    )


def _get_line_client(request: Request) -> LineClient:
    return cast(LineClient, request.app.state.line_client)


def _get_lodging_link_service(request: Request) -> LodgingLinkService:
    return cast(LodgingLinkService, request.app.state.lodging_link_service)


def _get_notion_sync_repository(request: Request) -> NotionSyncRepository | None:
    return cast(NotionSyncRepository | None, request.app.state.notion_sync_repository)


def _get_notion_sync_service(request: Request) -> NotionLodgingSyncService | None:
    return cast(
        NotionLodgingSyncService | None,
        request.app.state.notion_sync_service,
    )


def _get_map_enrichment_repository(
    request: Request,
) -> MapEnrichmentRepository | None:
    return cast(MapEnrichmentRepository | None, request.app.state.map_enrichment_repository)


def _get_map_enrichment_service(
    request: Request,
) -> LodgingMapEnrichmentService | None:
    return cast(
        LodgingMapEnrichmentService | None,
        request.app.state.map_enrichment_service,
    )


@router.post("/webhooks/line", response_model=LineWebhookResponse)
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(
        default=None,
        alias="X-Line-Signature",
    ),
) -> LineWebhookResponse:
    settings = _get_settings(request)
    body = await request.body()

    ensure_line_webhook_request_is_valid(
        settings=settings,
        body=body,
        signature=x_line_signature,
    )
    payload = parse_line_webhook_payload(body)
    captured = await process_events(
        payload=payload,
        settings=settings,
        repository=_get_captured_link_repository(request),
        line_client=_get_line_client(request),
        lodging_link_service=_get_lodging_link_service(request),
        notion_sync_repository=_get_notion_sync_repository(request),
        notion_sync_service=_get_notion_sync_service(request),
        map_enrichment_repository=_get_map_enrichment_repository(request),
        map_enrichment_service=_get_map_enrichment_service(request),
    )
    return LineWebhookResponse(ok=True, captured=captured)
