from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.collector import Collector, create_collector
from app.config import Settings
from app.itinerary import (
    GeminiItineraryProvider,
    ItineraryImportService,
)
from app.line_client import HttpLineClient, LineClient, NoopLineClient
from app.lodging_summary import (
    DecisionSummaryService,
    GeminiDecisionSummaryClient,
    LodgingDecisionSummaryService,
)
from app.lodging_links import HttpLodgingUrlResolver, LodgingLinkService
from app.map_enrichment import (
    BankOfTaiwanTwdPriceConverter,
    HttpLodgingPageFetcher,
    LodgingMapEnrichmentService,
    MapEnrichmentRepository,
    MongoMapEnrichmentRepository,
)
from app.trip_display import MongoTripDisplayRepository, TripDisplayRepository
from app.controllers.repositories import (
    ItineraryRepository,
    MessageSnapshotRepository,
    MongoItineraryRepository,
    MongoMessageSnapshotRepository,
    MongoTripRepository,
    TripRepository,
)
from app.routers import (
    health_router,
    line_webhook_router,
    map_enrichment_router,
    trip_display_router,
)


def create_app(
    settings: Settings | None = None,
    collector: Collector | None = None,
    line_client: LineClient | None = None,
    lodging_link_service: LodgingLinkService | None = None,
    map_enrichment_repository: MapEnrichmentRepository | None = None,
    map_enrichment_service: LodgingMapEnrichmentService | None = None,
    trip_repository: TripRepository | None = None,
    message_snapshot_repository: MessageSnapshotRepository | None = None,
    itinerary_repository: ItineraryRepository | None = None,
    itinerary_import_service: ItineraryImportService | None = None,
    trip_display_repository: TripDisplayRepository | None = None,
    decision_summary_service: DecisionSummaryService | None = None,
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
    if trip_repository is not None:
        active_trip_repository = trip_repository
    elif hasattr(active_collector, "collection") and hasattr(
        active_collector.collection,
        "database",
    ):
        active_trip_repository = MongoTripRepository(
            active_collector.collection.database[active_settings.trip_collection]
        )
    else:
        active_trip_repository = None
    if message_snapshot_repository is not None:
        active_message_snapshot_repository = message_snapshot_repository
    elif hasattr(active_collector, "collection") and hasattr(
        active_collector.collection,
        "database",
    ):
        active_message_snapshot_repository = MongoMessageSnapshotRepository(
            active_collector.collection.database[
                active_settings.line_message_snapshot_collection
            ]
        )
    else:
        active_message_snapshot_repository = None
    if itinerary_repository is not None:
        active_itinerary_repository = itinerary_repository
    elif hasattr(active_collector, "collection") and hasattr(
        active_collector.collection,
        "database",
    ):
        database = active_collector.collection.database
        active_itinerary_repository = MongoItineraryRepository(
            source_collection=database[active_settings.itinerary_source_collection],
            draft_collection=database[active_settings.itinerary_draft_collection],
            item_collection=database[active_settings.itinerary_item_collection],
        )
    else:
        active_itinerary_repository = None
    if itinerary_import_service is not None:
        active_itinerary_import_service = itinerary_import_service
    elif active_itinerary_repository is not None:
        provider = (
            GeminiItineraryProvider(
                active_settings.gemini_api_key,
                model=active_settings.gemini_model,
                timeout=active_settings.gemini_request_timeout,
            )
            if active_settings.is_gemini_configured
            else None
        )
        active_itinerary_import_service = ItineraryImportService(
            active_itinerary_repository,
            provider,
            timezone_name=active_settings.itinerary_default_timezone,
        )
    else:
        active_itinerary_import_service = None
    if trip_display_repository is not None:
        active_trip_display_repository = trip_display_repository
    elif hasattr(active_collector, "collection"):
        active_trip_display_repository = MongoTripDisplayRepository(
            active_collector.collection,
        )
    else:
        active_trip_display_repository = None
    if decision_summary_service is not None:
        active_decision_summary_service = decision_summary_service
    elif (
        active_settings.is_gemini_configured
        and active_trip_display_repository is not None
    ):
        active_decision_summary_service = LodgingDecisionSummaryService(
            active_trip_display_repository,
            GeminiDecisionSummaryClient(
                active_settings.gemini_api_key,
                model=active_settings.gemini_model,
                timeout=active_settings.gemini_request_timeout,
            ),
        )
    else:
        active_decision_summary_service = None

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
    app.state.trip_repository = active_trip_repository
    app.state.message_snapshot_repository = active_message_snapshot_repository
    app.state.itinerary_repository = active_itinerary_repository
    app.state.itinerary_import_service = active_itinerary_import_service
    app.state.trip_display_repository = active_trip_display_repository
    app.state.decision_summary_service = active_decision_summary_service

    app.include_router(health_router)
    app.include_router(line_webhook_router)
    app.include_router(map_enrichment_router)
    app.include_router(trip_display_router)

    return app


app = create_app()
