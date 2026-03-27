from __future__ import annotations

import asyncio

from app.collector import create_collector
from app.config import Settings
from app.notion_sync import (
    HttpNotionClient,
    MongoNotionSyncRepository,
    NotionLodgingSyncService,
    run_notion_sync_job,
)


def main() -> None:
    settings = Settings.from_env()
    collector, mongo_client = create_collector(settings)
    try:
        if not hasattr(collector, "collection"):
            raise RuntimeError("MongoDB collection is not available for Notion sync.")
        if not settings.notion_api_token:
            raise RuntimeError("NOTION_API_TOKEN is required for Notion sync.")
        if not settings.notion_data_source_id:
            raise RuntimeError(
                "NOTION_DATA_SOURCE_ID is required for Notion sync. "
                "Use /jobs/notion-sync/setup first if needed."
            )

        repository = MongoNotionSyncRepository(collector.collection)
        service = NotionLodgingSyncService(
            HttpNotionClient(
                settings.notion_api_token,
                timeout=settings.notion_request_timeout,
                api_version=settings.notion_api_version,
            ),
            parent_page_id=settings.notion_parent_page_id,
            database_id=settings.notion_database_id,
            data_source_id=settings.notion_data_source_id,
            database_title=settings.notion_database_title,
        )
        summary = asyncio.run(
            run_notion_sync_job(
                repository=repository,
                service=service,
                limit=settings.notion_sync_batch_size,
            )
        )
        print(
            "Notion sync finished: "
            f"processed={summary.processed} "
            f"created={summary.created} "
            f"updated={summary.updated} "
            f"failed={summary.failed}"
        )
    finally:
        if mongo_client is not None:
            mongo_client.close()


if __name__ == "__main__":
    main()
