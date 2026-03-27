from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.config import Settings
from app.controllers.notion_sync_controller import (
    build_notion_sync_documents_response,
    retry_notion_sync_document,
    setup_notion_database,
    trigger_notion_sync_run,
)
from app.notion_sync import NotionLodgingSyncService, NotionSyncRepository
from app.schemas.base import BaseResponse
from app.schemas.notion_sync import (
    NotionSetupRequest,
    NotionSetupResponse,
    NotionSyncDocumentsResponse,
    NotionSyncRetryResponse,
    NotionSyncRunRequest,
    NotionSyncRunResponse,
)

router = APIRouter(tags=["notion-sync"])


def _get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _get_notion_sync_repository(request: Request) -> NotionSyncRepository | None:
    return cast(NotionSyncRepository | None, request.app.state.notion_sync_repository)


def _get_notion_sync_service(request: Request) -> NotionLodgingSyncService | None:
    return cast(
        NotionLodgingSyncService | None,
        request.app.state.notion_sync_service,
    )


def _require_setup_service(request: Request) -> NotionLodgingSyncService:
    service = _get_notion_sync_service(request)
    if service is None or not service.is_setup_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "Notion setup is not configured. "
                "Set NOTION_API_TOKEN and NOTION_PARENT_PAGE_ID."
            ),
        )

    return service


def _require_run_dependencies(
    request: Request,
) -> tuple[NotionSyncRepository, NotionLodgingSyncService]:
    repository = _get_notion_sync_repository(request)
    service = _get_notion_sync_service(request)
    if repository is None or service is None or not service.is_sync_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "Notion sync is not configured. "
                "Set NOTION_API_TOKEN and NOTION_DATA_SOURCE_ID, "
                "or call /jobs/notion-sync/setup first."
            ),
        )

    return repository, service


@router.post(
    "/jobs/notion-sync/setup",
    response_model=BaseResponse[NotionSetupResponse],
)
async def create_notion_database(
    request: Request,
    payload: NotionSetupRequest | None = Body(default=None),
) -> BaseResponse[NotionSetupResponse]:
    settings = _get_settings(request)
    service = _require_setup_service(request)
    response = await setup_notion_database(
        service=service,
        title=payload.title if payload else None,
    )
    settings.notion_database_id = response.database_id
    settings.notion_data_source_id = response.data_source_id
    return BaseResponse(
        is_success=True,
        message="Notion database is ready for lodging sync.",
        data=response,
    )


@router.post(
    "/jobs/notion-sync/run",
    response_model=BaseResponse[NotionSyncRunResponse],
)
async def run_notion_sync(
    request: Request,
    payload: NotionSyncRunRequest | None = Body(default=None),
) -> BaseResponse[NotionSyncRunResponse]:
    settings = _get_settings(request)
    repository, service = _require_run_dependencies(request)
    limit = (
        payload.limit
        if payload and payload.limit is not None
        else settings.notion_sync_batch_size
    )
    force = payload.force if payload else False
    return BaseResponse(
        is_success=True,
        message="Notion sync job finished.",
        data=await trigger_notion_sync_run(
            repository=repository,
            service=service,
            limit=limit,
            force=force,
        ),
    )


@router.get(
    "/jobs/notion-sync/documents",
    response_model=BaseResponse[NotionSyncDocumentsResponse],
)
async def list_notion_sync_documents(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    status: list[str] | None = Query(default=None),
) -> BaseResponse[NotionSyncDocumentsResponse]:
    repository = _get_notion_sync_repository(request)
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail="Notion sync repository is not configured.",
        )

    return BaseResponse(
        is_success=True,
        message="Fetched Notion sync documents.",
        data=build_notion_sync_documents_response(
            repository=repository,
            limit=limit,
            statuses=status or [],
        ),
    )


@router.post(
    "/jobs/notion-sync/documents/{document_id}/retry",
    response_model=BaseResponse[NotionSyncRetryResponse],
)
async def retry_notion_sync_by_document_id(
    request: Request,
    document_id: str,
) -> BaseResponse[NotionSyncRetryResponse]:
    repository, service = _require_run_dependencies(request)
    result = await retry_notion_sync_document(
        repository=repository,
        service=service,
        document_id=document_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Notion sync document not found.",
        )

    return BaseResponse(
        is_success=True,
        message="Notion sync retry finished.",
        data=result,
    )
