from __future__ import annotations

from typing import Sequence

from app.notion_sync import (
    NotionLodgingSyncService,
    NotionSyncRepository,
    run_notion_sync_job,
)
from app.schemas.notion_sync import (
    NotionSetupResponse,
    NotionSyncDocumentResponse,
    NotionSyncDocumentsResponse,
    NotionSyncRetryResponse,
    NotionSyncRunResponse,
)


async def setup_notion_database(
    service: NotionLodgingSyncService,
    *,
    title: str | None = None,
) -> NotionSetupResponse:
    target = await service.setup_database(title=title)
    return NotionSetupResponse(
        database_id=target.database_id,
        data_source_id=target.data_source_id,
        database_title=target.title,
    )


async def trigger_notion_sync_run(
    repository: NotionSyncRepository,
    service: NotionLodgingSyncService,
    *,
    limit: int,
    force: bool = False,
) -> NotionSyncRunResponse:
    summary = await run_notion_sync_job(
        repository=repository,
        service=service,
        limit=limit,
        force=force,
    )
    return NotionSyncRunResponse(
        processed=summary.processed,
        created=summary.created,
        updated=summary.updated,
        failed=summary.failed,
        limit_used=limit,
        database_id=service.database_id or None,
        data_source_id=service.data_source_id or None,
    )


async def retry_notion_sync_document(
    repository: NotionSyncRepository,
    service: NotionLodgingSyncService,
    *,
    document_id: str,
) -> NotionSyncRetryResponse | None:
    candidate = repository.find_by_document_id(document_id)
    if candidate is None:
        return None

    try:
        result = await service.sync_document(candidate)
    except Exception as error:
        repository.mark_failed(candidate.document_id, str(error))
        return NotionSyncRetryResponse(
            document_id=document_id,
            processed=1,
            created=0,
            updated=0,
            failed=1,
        )

    repository.mark_synced(
        candidate.document_id,
        page_id=result.page_id,
        page_url=result.page_url,
    )
    return NotionSyncRetryResponse(
        document_id=document_id,
        processed=1,
        created=1 if result.created else 0,
        updated=0 if result.created else 1,
        failed=0,
        notion_page_id=result.page_id,
        notion_page_url=result.page_url,
    )


def build_notion_sync_documents_response(
    repository: NotionSyncRepository,
    *,
    limit: int,
    statuses: Sequence[str] | None = None,
) -> NotionSyncDocumentsResponse:
    normalized_statuses = [status for status in (statuses or []) if status]
    documents = [
        NotionSyncDocumentResponse(
            document_id=item.document_id,
            platform=item.platform,
            url=item.url,
            resolved_url=item.resolved_url,
            property_name=item.property_name,
            formatted_address=item.formatted_address,
            city=item.city,
            country_code=item.country_code,
            property_type=item.property_type,
            amenities=list(item.amenities),
            price_amount=item.price_amount,
            price_currency=item.price_currency,
            is_sold_out=item.is_sold_out,
            google_maps_url=item.google_maps_url,
            google_maps_search_url=item.google_maps_search_url,
            map_status=item.map_status,
            details_status=item.details_status,
            pricing_status=item.pricing_status,
            notion_page_id=item.notion_page_id,
            notion_page_url=item.notion_page_url,
            notion_sync_status=item.notion_sync_status,
            notion_sync_error=item.notion_sync_error,
            notion_sync_retry_count=item.notion_sync_retry_count,
            notion_last_attempt_at=item.notion_last_attempt_at,
            notion_last_synced_at=item.notion_last_synced_at,
            captured_at=item.captured_at,
        )
        for item in repository.list_documents(limit=limit, statuses=normalized_statuses)
    ]
    return NotionSyncDocumentsResponse(
        documents=documents,
        count=len(documents),
        limit_used=limit,
        statuses=normalized_statuses,
    )
