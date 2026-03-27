from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.collector import Collector, create_collector
from app.config import Settings
from app.line_client import HttpLineClient, LineClient, NoopLineClient
from app.lodging_links import HttpLodgingUrlResolver, LodgingLinkService
from app.map_enrichment import (
    BankOfTaiwanTwdPriceConverter,
    HttpLodgingPageFetcher,
    LodgingMapEnrichmentService,
    MapEnrichmentRepository,
    MongoMapEnrichmentRepository,
)
from app.notion_sync import (
    HttpNotionClient,
    MongoNotionSyncRepository,
    NotionLodgingSyncService,
    NotionSyncRepository,
)
from app.routers import (
    health_router,
    line_webhook_router,
    map_enrichment_router,
    notion_sync_router,
)


def create_app(
    settings: Settings | None = None,
    collector: Collector | None = None,
    line_client: LineClient | None = None,
    lodging_link_service: LodgingLinkService | None = None,
    map_enrichment_repository: MapEnrichmentRepository | None = None,
    map_enrichment_service: LodgingMapEnrichmentService | None = None,
    notion_sync_repository: NotionSyncRepository | None = None,
    notion_sync_service: NotionLodgingSyncService | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    owned_resource = None
    if collector is None:
        active_collector, owned_resource = create_collector(active_settings)
    else:
        active_collector = collector
    active_line_client = line_client or (
        HttpLineClient(active_settings.line_channel_access_token)
        if active_settings.line_channel_access_token
        else NoopLineClient()
    )
    active_lodging_link_service = lodging_link_service or LodgingLinkService(
        HttpLodgingUrlResolver()
    )
    active_map_enrichment_service = map_enrichment_service or LodgingMapEnrichmentService(
        HttpLodgingPageFetcher(active_settings.map_enrichment_request_timeout),
        HttpLodgingUrlResolver(active_settings.map_enrichment_request_timeout),
        BankOfTaiwanTwdPriceConverter(
            timeout=active_settings.map_enrichment_request_timeout
        ),
    )
    if map_enrichment_repository is not None:
        active_map_enrichment_repository = map_enrichment_repository
    elif hasattr(active_collector, "collection"):
        active_map_enrichment_repository = MongoMapEnrichmentRepository(
            active_collector.collection,
            max_retry_count=active_settings.map_enrichment_max_retry_count,
        )
    else:
        active_map_enrichment_repository = None
    if notion_sync_repository is not None:
        active_notion_sync_repository = notion_sync_repository
    elif hasattr(active_collector, "collection"):
        active_notion_sync_repository = MongoNotionSyncRepository(
            active_collector.collection
        )
    else:
        active_notion_sync_repository = None
    active_notion_sync_service = notion_sync_service or (
        NotionLodgingSyncService(
            HttpNotionClient(
                active_settings.notion_api_token,
                timeout=active_settings.notion_request_timeout,
                api_version=active_settings.notion_api_version,
            ),
            parent_page_id=active_settings.notion_parent_page_id,
            database_id=active_settings.notion_database_id,
            data_source_id=active_settings.notion_data_source_id,
            database_title=active_settings.notion_database_title,
        )
        if active_settings.notion_api_token
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if owned_resource is not None:
                owned_resource.close()

    app = FastAPI(
        title="Nihon Line Bot",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.collector = active_collector
    app.state.captured_link_repository = active_collector
    app.state.line_client = active_line_client
    app.state.lodging_link_service = active_lodging_link_service
    app.state.map_enrichment_repository = active_map_enrichment_repository
    app.state.map_enrichment_service = active_map_enrichment_service
    app.state.notion_sync_repository = active_notion_sync_repository
    app.state.notion_sync_service = active_notion_sync_service

    app.include_router(health_router)
    app.include_router(line_webhook_router)
    app.include_router(map_enrichment_router)
    app.include_router(notion_sync_router)

    return app


app = create_app()
