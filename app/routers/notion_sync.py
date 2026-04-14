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
from app.notion_sync import (
    NotionTargetManager,
    NotionSyncRepository,
    build_source_scope,
)
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


def _get_notion_target_manager(request: Request) -> NotionTargetManager:
    return cast(NotionTargetManager, request.app.state.notion_target_manager)


def _require_run_dependencies(
    request: Request,
) -> tuple[NotionSyncRepository, NotionTargetManager]:
    repository = _get_notion_sync_repository(request)
    manager = _get_notion_target_manager(request)
    if repository is None or manager.default_service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Notion sync is not configured. "
                "Set NOTION_API_TOKEN and NOTION_DATA_SOURCE_ID, "
                "or call /jobs/notion-sync/setup first."
            ),
        )

    return repository, manager


def _parse_source_scope(
    *,
    source_type: str | None,
    group_id: str | None,
    room_id: str | None,
    user_id: str | None,
    trip_id: str | None = None,
    trip_title: str | None = None,
):
    try:
        return build_source_scope(
            source_type=source_type,
            group_id=group_id,
            room_id=room_id,
            user_id=user_id,
            trip_id=trip_id,
            trip_title=trip_title,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/jobs/notion-sync/setup",
    response_model=BaseResponse[NotionSetupResponse],
)
async def create_notion_database(
    request: Request,
    payload: NotionSetupRequest | None = Body(default=None),
) -> BaseResponse[NotionSetupResponse]:
    settings = _get_settings(request)
    manager = _get_notion_target_manager(request)
    if manager.default_service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Notion setup is not configured. "
                "Set NOTION_API_TOKEN plus NOTION_PARENT_PAGE_ID "
                "or an existing NOTION_DATA_SOURCE_ID."
            ),
        )

    source_scope = _parse_source_scope(
        source_type=payload.source_type if payload else None,
        group_id=payload.group_id if payload else None,
        room_id=payload.room_id if payload else None,
        user_id=payload.user_id if payload else None,
        trip_id=payload.trip_id if payload else None,
        trip_title=payload.trip_title if payload else None,
    )

    try:
        response = await setup_notion_database(
            manager=manager,
            title=payload.title if payload else None,
            source_scope=source_scope,
            parent_page_id=payload.parent_page_id if payload else None,
            data_source_id=payload.data_source_id if payload else None,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503 if source_scope is None else 422,
            detail=(
                "Notion setup is not configured. "
                "Set NOTION_API_TOKEN plus NOTION_PARENT_PAGE_ID "
                "or an existing NOTION_DATA_SOURCE_ID."
                if source_scope is None
                else (
                    "Scoped Notion setup requires `parent_page_id` or "
                    "`data_source_id`, or an existing scoped target."
                )
            ),
        ) from error

    if source_scope is None:
        settings.notion_database_id = response.database_id
        settings.notion_data_source_id = response.data_source_id
        settings.notion_database_url = response.database_url or ""
        settings.notion_public_database_url = response.database_public_url or ""

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
    repository, manager = _require_run_dependencies(request)
    limit = (
        payload.limit
        if payload and payload.limit is not None
        else settings.notion_sync_batch_size
    )
    force = payload.force if payload else False
    source_scope = _parse_source_scope(
        source_type=payload.source_type if payload else None,
        group_id=payload.group_id if payload else None,
        room_id=payload.room_id if payload else None,
        user_id=payload.user_id if payload else None,
        trip_id=payload.trip_id if payload else None,
        trip_title=payload.trip_title if payload else None,
    )

    try:
        response = await trigger_notion_sync_run(
            repository=repository,
            manager=manager,
            limit=limit,
            force=force,
            source_scope=source_scope,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Notion sync is not configured. "
                "Set NOTION_API_TOKEN and NOTION_DATA_SOURCE_ID, "
                "or call /jobs/notion-sync/setup first."
            ),
        ) from error

    return BaseResponse(
        is_success=True,
        message="Notion sync job finished.",
        data=response,
    )


@router.get(
    "/jobs/notion-sync/documents",
    response_model=BaseResponse[NotionSyncDocumentsResponse],
)
async def list_notion_sync_documents(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    status: list[str] | None = Query(default=None),
    source_type: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    room_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    trip_id: str | None = Query(default=None),
) -> BaseResponse[NotionSyncDocumentsResponse]:
    repository = _get_notion_sync_repository(request)
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail="Notion sync repository is not configured.",
        )

    source_scope = _parse_source_scope(
        source_type=source_type,
        group_id=group_id,
        room_id=room_id,
        user_id=user_id,
        trip_id=trip_id,
    )

    return BaseResponse(
        is_success=True,
        message="Fetched Notion sync documents.",
        data=build_notion_sync_documents_response(
            repository=repository,
            limit=limit,
            statuses=status or [],
            source_scope=source_scope,
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
    repository, manager = _require_run_dependencies(request)
    result = await retry_notion_sync_document(
        repository=repository,
        manager=manager,
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
