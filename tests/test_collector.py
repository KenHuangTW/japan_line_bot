from __future__ import annotations

from datetime import datetime

from app.collector import create_collector
from app.config import Settings
from app.controllers.repositories.captured_link_repository import (
    JsonlCapturedLinkRepository,
    MongoCapturedLinkRepository,
)
from app.models import CapturedLodgingLink


class FakeInsertManyResult:
    def __init__(self, count: int) -> None:
        self.inserted_ids = list(range(count))


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []
        self.ordered: bool | None = None

    def insert_many(
        self,
        documents: list[dict[str, object]],
        ordered: bool = True,
    ) -> FakeInsertManyResult:
        self.documents.extend(documents)
        self.ordered = ordered
        return FakeInsertManyResult(len(documents))


class FakeDatabase:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.requested_collections: list[str] = []

    def __getitem__(self, name: str) -> FakeCollection:
        self.requested_collections.append(name)
        return self.collection


class FakeMongoClient:
    def __init__(self, uri: str, tz_aware: bool = False) -> None:
        self.uri = uri
        self.tz_aware = tz_aware
        self.collection = FakeCollection()
        self.database = FakeDatabase(self.collection)
        self.requested_databases: list[str] = []
        self.closed = False

    def __getitem__(self, name: str) -> FakeDatabase:
        self.requested_databases.append(name)
        return self.database

    def close(self) -> None:
        self.closed = True


def _sample_link(url: str) -> CapturedLodgingLink:
    return CapturedLodgingLink(
        platform="booking",
        url=url,
        hostname="www.booking.com",
        message_text=f"請看 {url}",
        source_type="group",
        group_id="Cgroup123",
        user_id="Uuser123",
        message_id="325708",
        event_timestamp_ms=1711111111111,
        event_mode="active",
    )


def test_mongo_captured_link_repository_appends_many_records() -> None:
    collection = FakeCollection()
    repository = MongoCapturedLinkRepository(collection)

    appended = repository.append_many(
        [
            _sample_link("https://www.booking.com/hotel/jp/foo.html"),
            _sample_link("https://www.booking.com/hotel/jp/bar.html"),
        ]
    )

    assert appended == 2
    assert collection.ordered is True
    assert [document["url"] for document in collection.documents] == [
        "https://www.booking.com/hotel/jp/foo.html",
        "https://www.booking.com/hotel/jp/bar.html",
    ]
    assert isinstance(collection.documents[0]["captured_at"], datetime)


def test_create_collector_uses_mongo_backend() -> None:
    created_clients: list[FakeMongoClient] = []

    def fake_factory(uri: str, tz_aware: bool = False) -> FakeMongoClient:
        client = FakeMongoClient(uri, tz_aware=tz_aware)
        created_clients.append(client)
        return client

    settings = Settings(
        storage_backend="mongo",
        mongo_uri="mongodb://mongo:27017",
        mongo_database="nihon_line_bot",
        mongo_collection="captured_links",
    )

    collector, resource = create_collector(
        settings,
        mongo_client_factory=fake_factory,
    )

    assert isinstance(collector, MongoCapturedLinkRepository)
    assert resource is created_clients[0]
    assert created_clients[0].uri == "mongodb://mongo:27017"
    assert created_clients[0].tz_aware is True
    assert created_clients[0].requested_databases == ["nihon_line_bot"]
    assert created_clients[0].database.requested_collections == ["captured_links"]


def test_create_collector_uses_jsonl_backend(tmp_path) -> None:
    output_path = tmp_path / "captured.jsonl"
    settings = Settings(
        storage_backend="jsonl",
        collector_output_path=output_path,
    )

    collector, resource = create_collector(settings)

    assert isinstance(collector, JsonlCapturedLinkRepository)
    assert resource is None


def test_storage_target_redacts_password() -> None:
    settings = Settings(
        storage_backend="mongo",
        mongo_uri="mongodb://line-bot:super-secret@mongo:27017",
        mongo_database="nihon_line_bot",
        mongo_collection="captured_links",
    )

    assert (
        settings.storage_target
        == "mongodb://line-bot:***@mongo:27017/nihon_line_bot.captured_links"
    )
