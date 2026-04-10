from __future__ import annotations

import asyncio

from app.notion_sync.models import NotionDatabaseTarget, NotionSyncSourceScope
from app.notion_sync.service import NotionLodgingSyncService
from app.notion_sync.targets import (
    MongoNotionTargetRepository,
    NotionTargetConfig,
    NotionTargetManager,
)


class InMemoryCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []

    def find_one(self, filter: dict[str, object], *args, **kwargs):
        for document in self.documents:
            if all(document.get(key) == value for key, value in filter.items()):
                return dict(document)
        return None

    def update_one(self, filter: dict[str, object], update: dict[str, object], *args, **kwargs):
        document = self.find_one(filter) or {}
        set_fields = dict(update.get("$set", {}))
        set_on_insert = dict(update.get("$setOnInsert", {})) if not document else {}
        document.update(set_on_insert)
        document.update(set_fields)
        for index, existing in enumerate(self.documents):
            if all(existing.get(key) == value for key, value in filter.items()):
                self.documents[index] = document
                break
        else:
            self.documents.append(document)


class FakeNotionClient:
    async def create_database(
        self,
        *,
        parent_page_id: str,
        title: str,
    ) -> NotionDatabaseTarget:
        suffix = parent_page_id.removeprefix("page-")
        return NotionDatabaseTarget(
            database_id=f"db-{suffix}",
            data_source_id=f"ds-{suffix}",
            title=title,
            url=f"https://www.notion.so/workspace/db-{suffix}?v=view-{suffix}",
            public_url=f"https://www.notion.so/public-db-{suffix}",
        )

    async def retrieve_database(self, *, database_id: str) -> dict[str, object]:
        raise NotImplementedError

    async def retrieve_data_source(self, *, data_source_id: str) -> dict[str, object]:
        raise NotImplementedError

    async def update_data_source(
        self,
        *,
        data_source_id: str,
        title: str,
        properties: dict[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError

    async def retrieve_page(self, *, page_id: str) -> dict[str, object]:
        raise NotImplementedError

    async def create_page(self, *, data_source_id: str, properties: dict[str, object]):
        raise NotImplementedError

    async def update_page(self, *, page_id: str, properties: dict[str, object]):
        raise NotImplementedError


def test_mongo_notion_target_repository_round_trips_scoped_target() -> None:
    repository = MongoNotionTargetRepository(InMemoryCollection())
    source_scope = NotionSyncSourceScope(source_type="group", group_id="group-123")
    target = NotionTargetConfig.from_source_scope(
        source_scope,
        parent_page_id="page-group-123",
        database_id="db-group-123",
        data_source_id="ds-group-123",
        database_title="Group Trip",
        database_url="https://www.notion.so/workspace/db-group-123?v=view-group-123",
        public_database_url="https://www.notion.so/public-db-group-123",
    )

    repository.save(target)

    stored = repository.find_by_source_scope(source_scope)

    assert stored == target


def test_notion_target_manager_resolves_scoped_target_before_default() -> None:
    repository = MongoNotionTargetRepository(InMemoryCollection())
    source_scope = NotionSyncSourceScope(source_type="group", group_id="group-123")
    repository.save(
        NotionTargetConfig.from_source_scope(
            source_scope,
            parent_page_id="page-group-123",
            database_id="db-group-123",
            data_source_id="ds-group-123",
            database_title="Group Trip",
            database_url="https://www.notion.so/workspace/db-group-123?v=view-group-123",
            public_database_url="https://www.notion.so/public-db-group-123",
        )
    )
    default_service = NotionLodgingSyncService(
        FakeNotionClient(),
        parent_page_id="page-default",
        database_id="db-default",
        data_source_id="ds-default",
        database_title="Default Trip",
        database_url="https://www.notion.so/workspace/db-default?v=view-default",
        public_database_url="https://www.notion.so/public-db-default",
    )
    manager = NotionTargetManager(default_service, repository)

    resolved = manager.resolve_service(source_scope)

    assert resolved is not None
    assert resolved.target_source == "scoped"
    assert resolved.service.data_source_id == "ds-group-123"
    assert default_service.data_source_id == "ds-default"


def test_notion_target_manager_setup_database_persists_scoped_target() -> None:
    repository = MongoNotionTargetRepository(InMemoryCollection())
    default_service = NotionLodgingSyncService(
        FakeNotionClient(),
        database_title="Nihon LINE Bot Lodgings",
    )
    manager = NotionTargetManager(default_service, repository)
    source_scope = NotionSyncSourceScope(source_type="room", room_id="room-123")

    resolved = asyncio.run(
        manager.setup_database(
            title="Room Trip",
            source_scope=source_scope,
            parent_page_id="page-room-123",
        )
    )

    assert resolved is not None
    assert resolved.target_source == "scoped"
    stored = repository.find_by_source_scope(source_scope)
    assert stored is not None
    assert stored.parent_page_id == "page-room-123"
    assert stored.database_id == "db-room-123"
    assert stored.data_source_id == "ds-room-123"
    assert stored.database_title == "Room Trip"
