from __future__ import annotations

from typing import Sequence

from app.map_enrichment import (
    LodgingMapEnrichmentService,
    MapEnrichmentRepository,
    MapEnrichmentSummary,
    retry_all_map_enrichment_documents,
    retry_all_failed_map_enrichment_documents,
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
    return _build_run_response(summary=summary, limit=limit)


async def trigger_retry_all_map_enrichment_run(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    limit: int | None = None,
) -> MapEnrichmentRunResponse:
    summary = await retry_all_map_enrichment_documents(
        repository=repository,
        service=service,
        limit=limit,
    )
    effective_limit = limit if limit is not None else summary.processed
    return _build_run_response(summary=summary, limit=effective_limit)


async def trigger_retry_all_failed_map_enrichment_run(
    repository: MapEnrichmentRepository,
    service: LodgingMapEnrichmentService,
    limit: int,
) -> MapEnrichmentRunResponse:
    summary = await retry_all_failed_map_enrichment_documents(
        repository=repository,
        service=service,
        limit=limit,
    )
    return _build_run_response(summary=summary, limit=limit)


def _build_run_response(
    *,
    summary: MapEnrichmentSummary,
    limit: int,
) -> MapEnrichmentRunResponse:
    return MapEnrichmentRunResponse(
        processed=summary.processed,
        resolved=summary.resolved,
        partial=summary.partial,
        details_resolved=summary.details_resolved,
        pricing_resolved=summary.pricing_resolved,
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
            partial=0,
            details_resolved=0,
            pricing_resolved=0,
            failed=1,
        )

    if enrichment is None:
        repository.mark_failed(
            candidate.document_id,
            "No lodging metadata could be extracted from lodging page.",
        )
        return MapEnrichmentRetryResponse(
            document_id=document_id,
            processed=1,
            resolved=0,
            partial=0,
            details_resolved=0,
            pricing_resolved=0,
            failed=1,
        )

    repository.mark_resolved(candidate.document_id, enrichment)
    return MapEnrichmentRetryResponse(
        document_id=document_id,
        processed=1,
        resolved=1 if enrichment.has_coordinates else 0,
        partial=0 if enrichment.has_coordinates else 1,
        details_resolved=1 if enrichment.has_details else 0,
        pricing_resolved=1 if enrichment.has_pricing else 0,
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
            details_status=item.details_status,
            details_source=item.details_source,
            pricing_status=item.pricing_status,
            pricing_source=item.pricing_source,
            property_name=item.property_name,
            formatted_address=item.formatted_address,
            street_address=item.street_address,
            district=item.district,
            city=item.city,
            region=item.region,
            postal_code=item.postal_code,
            country_name=item.country_name,
            country_code=item.country_code,
            latitude=item.latitude,
            longitude=item.longitude,
            property_type=item.property_type,
            room_count=item.room_count,
            bedroom_count=item.bedroom_count,
            bathroom_count=item.bathroom_count,
            amenities=list(item.amenities),
            price_amount=item.price_amount,
            price_currency=item.price_currency,
            source_price_amount=item.source_price_amount,
            source_price_currency=item.source_price_currency,
            price_exchange_rate=item.price_exchange_rate,
            price_exchange_rate_source=item.price_exchange_rate_source,
            is_sold_out=item.is_sold_out,
            availability_source=item.availability_source,
            google_maps_url=item.google_maps_url,
            google_maps_search_url=item.google_maps_search_url,
            map_error=item.map_error,
            map_retry_count=item.map_retry_count,
            details_error=item.details_error,
            details_retry_count=item.details_retry_count,
            pricing_error=item.pricing_error,
            pricing_retry_count=item.pricing_retry_count,
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
