from __future__ import annotations

from typing import Sequence

from app.notion_sync import (
    NotionTargetManager,
    NotionSyncRepository,
    run_notion_sync_job,
    sync_notion_document,
    source_scope_to_fields,
)
from app.notion_sync.models import NotionSyncSourceScope
from app.schemas.notion_sync import (
    NotionSetupResponse,
    NotionSyncDocumentResponse,
    NotionSyncDocumentsResponse,
    NotionSyncRetryResponse,
    NotionSyncRunResponse,
)


async def setup_notion_database(
    manager: NotionTargetManager,
    *,
    title: str | None = None,
    source_scope: NotionSyncSourceScope | None = None,
    parent_page_id: str | None = None,
    data_source_id: str | None = None,
) -> NotionSetupResponse:
    resolved_service = await manager.setup_database(
        title=title,
        source_scope=source_scope,
        parent_page_id=parent_page_id,
        data_source_id=data_source_id,
    )
    if resolved_service is None:
        raise RuntimeError("Notion setup is not configured.")

    target = resolved_service.target
    return NotionSetupResponse(
        database_id=target.database_id,
        data_source_id=target.data_source_id,
        database_title=target.database_title,
        database_url=target.database_url,
        database_public_url=target.public_database_url,
        target_source=resolved_service.target_source,
        **source_scope_to_fields(source_scope),
    )


async def trigger_notion_sync_run(
    repository: NotionSyncRepository,
    manager: NotionTargetManager,
    *,
    limit: int,
    force: bool = False,
    source_scope: NotionSyncSourceScope | None = None,
) -> NotionSyncRunResponse:
    resolved_service = manager.resolve_service(source_scope)
    if resolved_service is None or not resolved_service.service.is_sync_configured:
        raise RuntimeError("Notion sync is not configured.")

    if force:
        resolved_service = await manager.setup_database(
            source_scope=(
                source_scope if resolved_service.target_source == "scoped" else None
            )
        )
        if resolved_service is None or not resolved_service.service.is_sync_configured:
            raise RuntimeError("Notion sync is not configured.")

    summary = await run_notion_sync_job(
        repository=repository,
        service=resolved_service.service,
        limit=limit,
        force=force,
        source_scope=source_scope,
        target_manager=manager,
    )
    return NotionSyncRunResponse(
        processed=summary.processed,
        created=summary.created,
        updated=summary.updated,
        failed=summary.failed,
        limit_used=limit,
        database_id=resolved_service.service.database_id or None,
        data_source_id=resolved_service.service.data_source_id or None,
        target_source=resolved_service.target_source,
        **source_scope_to_fields(source_scope),
    )


async def retry_notion_sync_document(
    repository: NotionSyncRepository,
    manager: NotionTargetManager,
    *,
    document_id: str,
) -> NotionSyncRetryResponse | None:
    candidate = repository.find_by_document_id(document_id)
    if candidate is None:
        return None

    try:
        result = await sync_notion_document(
            repository=repository,
            service=manager.default_service,
            document_id=document_id,
            target_manager=manager,
        )
    except Exception as error:
        repository.mark_failed(candidate.document_id, str(error))
        return NotionSyncRetryResponse(
            document_id=document_id,
            processed=1,
            created=0,
            updated=0,
            failed=1,
        )

    if result is None:
        return None
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
    source_scope: NotionSyncSourceScope | None = None,
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
            source_type=item.source_type,
            group_id=item.group_id,
            room_id=item.room_id,
            user_id=item.user_id,
        )
        for item in repository.list_documents(
            limit=limit,
            statuses=normalized_statuses,
            source_scope=source_scope,
        )
    ]
    return NotionSyncDocumentsResponse(
        documents=documents,
        count=len(documents),
        limit_used=limit,
        statuses=normalized_statuses,
    )
