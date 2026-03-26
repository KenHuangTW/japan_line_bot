from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.config import Settings
from app.controllers.map_enrichment_controller import (
    build_map_enrichment_documents_response,
    retry_map_enrichment_document,
    trigger_map_enrichment_run,
    trigger_retry_all_map_enrichment_run,
)
from app.map_enrichment import LodgingMapEnrichmentService, MapEnrichmentRepository
from app.schemas.base import BaseResponse
from app.schemas.map_enrichment import (
    MapEnrichmentDocumentsResponse,
    MapEnrichmentRetryResponse,
    MapEnrichmentRunRequest,
    MapEnrichmentRunResponse,
)

router = APIRouter(tags=["lodging-enrichment"])


def _get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


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


def _require_dependencies(
    request: Request,
) -> tuple[MapEnrichmentRepository, LodgingMapEnrichmentService]:
    repository = _get_map_enrichment_repository(request)
    service = _get_map_enrichment_service(request)
    if repository is None or service is None:
        raise HTTPException(
            status_code=503,
            detail="Map enrichment dependencies are not configured.",
        )

    return repository, service


@router.post(
    "/jobs/lodging-enrichment/run",
    response_model=BaseResponse[MapEnrichmentRunResponse],
)
@router.post(
    "/jobs/map-enrichment/run",
    response_model=BaseResponse[MapEnrichmentRunResponse],
    include_in_schema=False,
)
async def run_map_enrichment(
    request: Request,
    payload: MapEnrichmentRunRequest | None = Body(default=None),
) -> BaseResponse[MapEnrichmentRunResponse]:
    settings = _get_settings(request)
    repository, service = _require_dependencies(request)
    limit = (
        payload.limit
        if payload and payload.limit is not None
        else settings.map_enrichment_batch_size
    )
    return BaseResponse(
        is_success=True,
        message="Lodging enrichment job finished.",
        data=await trigger_map_enrichment_run(
            repository=repository,
            service=service,
            limit=limit,
        ),
    )


@router.get(
    "/jobs/lodging-enrichment/documents",
    response_model=BaseResponse[MapEnrichmentDocumentsResponse],
)
@router.get(
    "/jobs/map-enrichment/documents",
    response_model=BaseResponse[MapEnrichmentDocumentsResponse],
    include_in_schema=False,
)
async def list_map_enrichment_documents(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    status: list[str] | None = Query(default=None),
) -> BaseResponse[MapEnrichmentDocumentsResponse]:
    repository = _get_map_enrichment_repository(request)
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail="Map enrichment repository is not configured.",
        )

    return BaseResponse(
        is_success=True,
        message="Fetched lodging enrichment documents.",
        data=build_map_enrichment_documents_response(
            repository=repository,
            limit=limit,
            statuses=status or [],
        ),
    )


@router.post(
    "/jobs/lodging-enrichment/documents/retry-all",
    response_model=BaseResponse[MapEnrichmentRunResponse],
)
@router.post(
    "/jobs/map-enrichment/documents/retry-all",
    response_model=BaseResponse[MapEnrichmentRunResponse],
    include_in_schema=False,
)
async def retry_all_map_enrichment_documents(
    request: Request,
    payload: MapEnrichmentRunRequest | None = Body(default=None),
) -> BaseResponse[MapEnrichmentRunResponse]:
    repository, service = _require_dependencies(request)
    limit = payload.limit if payload and payload.limit is not None else None
    return BaseResponse(
        is_success=True,
        message="Lodging enrichment bulk retry finished.",
        data=await trigger_retry_all_map_enrichment_run(
            repository=repository,
            service=service,
            limit=limit,
        ),
    )


@router.post(
    "/jobs/lodging-enrichment/documents/{document_id}/retry",
    response_model=BaseResponse[MapEnrichmentRetryResponse],
)
@router.post(
    "/jobs/map-enrichment/documents/{document_id}/retry",
    response_model=BaseResponse[MapEnrichmentRetryResponse],
    include_in_schema=False,
)
async def retry_map_enrichment_by_document_id(
    request: Request,
    document_id: str,
) -> BaseResponse[MapEnrichmentRetryResponse]:
    repository, service = _require_dependencies(request)
    result = await retry_map_enrichment_document(
        repository=repository,
        service=service,
        document_id=document_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Map enrichment document not found.",
        )

    return BaseResponse(
        is_success=True,
        message="Lodging enrichment retry finished.",
        data=result,
    )
