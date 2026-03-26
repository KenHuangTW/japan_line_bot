from __future__ import annotations

from typing import Sequence

from app.map_enrichment import (
    LodgingMapEnrichmentService,
    MapEnrichmentRepository,
    run_map_enrichment_job,
)
from app.schemas.map_enrichment import (
    MapEnrichmentDocumentResponse,
    MapEnrichmentDocumentsResponse,
    MapEnrichmentRetryResponse,
    MapEnrichmentRunResponse,
)


async def trigger_map_enrichment_run(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    limit: int,
) -> MapEnrichmentRunResponse:
    summary = await run_map_enrichment_job(
        repository=repository,
        service=service,
        limit=limit,
    )
    return MapEnrichmentRunResponse(
        processed=summary.processed,
        resolved=summary.resolved,
        failed=summary.failed,
        limit_used=limit,
    )


async def retry_map_enrichment_document(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    document_id: str,
) -> MapEnrichmentRetryResponse | None:
    candidate = repository.find_by_document_id(document_id)
    if candidate is None:
        return None

    try:
        enrichment = await service.enrich(candidate.target_url)
    except Exception as error:
        repository.mark_failed(candidate.document_id, str(error))
        return MapEnrichmentRetryResponse(
            document_id=document_id,
            processed=1,
            resolved=0,
            failed=1,
        )

    if enrichment is None:
        repository.mark_failed(
            candidate.document_id,
            "No map metadata could be extracted from lodging page.",
        )
        return MapEnrichmentRetryResponse(
            document_id=document_id,
            processed=1,
            resolved=0,
            failed=1,
        )

    repository.mark_resolved(candidate.document_id, enrichment)
    return MapEnrichmentRetryResponse(
        document_id=document_id,
        processed=1,
        resolved=1,
        failed=0,
    )


def build_map_enrichment_documents_response(
    repository: MapEnrichmentRepository,
    limit: int,
    statuses: Sequence[str] | None = None,
) -> MapEnrichmentDocumentsResponse:
    normalized_statuses = [status for status in (statuses or []) if status]
    documents = [
        MapEnrichmentDocumentResponse(
            document_id=item.document_id,
            url=item.url,
            resolved_url=item.resolved_url,
            map_status=item.map_status,
            map_source=item.map_source,
            property_name=item.property_name,
            formatted_address=item.formatted_address,
            latitude=item.latitude,
            longitude=item.longitude,
            google_maps_url=item.google_maps_url,
            map_error=item.map_error,
            map_retry_count=item.map_retry_count,
            captured_at=item.captured_at,
        )
        for item in repository.list_documents(limit=limit, statuses=normalized_statuses)
    ]
    return MapEnrichmentDocumentsResponse(
        documents=documents,
        count=len(documents),
        limit_used=limit,
        statuses=normalized_statuses,
    )
