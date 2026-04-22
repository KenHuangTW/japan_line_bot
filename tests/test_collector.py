from __future__ import annotations

from datetime import datetime

from app.collector import create_collector
from app.config import Settings
from app.controllers.repositories.mongo_captured_link_repository import (
    MongoCapturedLinkRepository,
)
from app.models import CapturedLodgingLink


class FakeInsertManyResult:
    def __init__(self, count: int) -> None:
        self.inserted_ids = list(range(count))


class FakeUpdateOneResult:
    def __init__(self, matched_count: int) -> None:
        self.matched_count = matched_count


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

    def find_one(self, filter: dict[str, object], *args, **kwargs) -> dict[str, object] | None:
        matched = [
            document
            for document in self.documents
            if _matches_fake_query(document, filter)
        ]
        sort = kwargs.get("sort")
        if sort:
            for field, direction in reversed(sort):
                matched.sort(
                    key=lambda item: item.get(field),
                    reverse=direction < 0,
                )
        return matched[0] if matched else None

    def find(self, query: dict[str, object]) -> list[dict[str, object]]:
        return [
            document for document in self.documents if _matches_fake_query(document, query)
        ]

    def update_one(
        self,
        filter: dict[str, object],
        update: dict[str, object],
        *args,
        **kwargs,
    ) -> FakeUpdateOneResult:
        for document in self.documents:
            if not _matches_fake_query(document, filter):
                continue
            set_values = update.get("$set")
            if isinstance(set_values, dict):
                document.update(set_values)
            return FakeUpdateOneResult(1)
        return FakeUpdateOneResult(0)


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


def _sample_link(
    url: str,
    *,
    platform: str = "booking",
    hostname: str = "www.booking.com",
) -> CapturedLodgingLink:
    return CapturedLodgingLink(
        platform=platform,
        url=url,
        hostname=hostname,
        message_text=f"請看 {url}",
        source_type="group",
        group_id="Cgroup123",
        user_id="Uuser123",
        message_id="325708",
        event_timestamp_ms=1711111111111,
        event_mode="active",
    )


def _matches_fake_query(document: dict[str, object], query: dict[str, object]) -> bool:
    for key, value in query.items():
        if key == "$and":
            assert isinstance(value, list)
            if not all(_matches_fake_query(document, clause) for clause in value):
                return False
            continue
        if key == "$or":
            assert isinstance(value, list)
            if not any(_matches_fake_query(document, clause) for clause in value):
                return False
            continue
        if key == "$expr":
            assert isinstance(value, dict)
            if not _matches_fake_expr(document, value):
                return False
            continue
        if isinstance(value, dict):
            if "$in" in value and document.get(key) not in value["$in"]:
                return False
            if "$ne" in value and document.get(key) == value["$ne"]:
                return False
            if "$regex" in value:
                pattern = value["$regex"]
                field_value = document.get(key)
                if (
                    not isinstance(field_value, str)
                    or pattern.search(field_value) is None
                ):
                    return False
            continue
        if document.get(key) != value:
            return False
    return True


def _matches_fake_expr(document: dict[str, object], expr: dict[str, object]) -> bool:
    operands = expr.get("$ne")
    if not isinstance(operands, list) or len(operands) != 2:
        raise AssertionError("Unsupported fake Mongo expression.")
    left, right = operands
    if isinstance(left, str) and left.startswith("$"):
        left = document.get(left[1:])
    if isinstance(right, str) and right.startswith("$"):
        right = document.get(right[1:])
    return left != right


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


def test_mongo_captured_link_repository_prefers_saved_short_link_for_duplicates() -> None:
    collection = FakeCollection()
    repository = MongoCapturedLinkRepository(collection)
    collection.documents.extend(
        [
            _sample_link("https://www.booking.com/Share-older").model_dump(mode="python")
            | {
                "resolved_url": "https://www.booking.com/hotel/jp/foo.html",
                "captured_at": datetime(2026, 3, 29),
            },
            _sample_link("https://www.booking.com/hotel/jp/foo.html").model_dump(mode="python")
            | {
                "resolved_url": "https://www.booking.com/hotel/jp/foo.html",
                "captured_at": datetime(2026, 3, 30),
            },
        ]
    )

    duplicate = repository.find_duplicate(
        ["https://www.booking.com/hotel/jp/foo.html"],
        source_type="group",
        group_id="Cgroup123",
    )

    assert duplicate is not None
    assert duplicate.url == "https://www.booking.com/Share-older"


def test_mongo_captured_link_repository_matches_duplicates_ignoring_query_string() -> None:
    collection = FakeCollection()
    repository = MongoCapturedLinkRepository(collection)
    collection.documents.append(
        _sample_link("https://www.agoda.com/sp/B70FF37xamn").model_dump(mode="python")
        | {
            "platform": "agoda",
            "hostname": "agoda.com",
            "resolved_url": (
                "https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"
                "?pid=redirect"
            ),
        }
    )

    duplicate = repository.find_duplicate(
        ["https://www.agoda.com/funhome-h40642218/hotel/nagoya-jp.html"],
        source_type="group",
        group_id="Cgroup123",
    )

    assert duplicate is not None
    assert duplicate.url == "https://www.agoda.com/sp/B70FF37xamn"


def test_mongo_captured_link_repository_matches_airbnb_duplicates_ignoring_www_and_query_string() -> None:
    collection = FakeCollection()
    repository = MongoCapturedLinkRepository(collection)
    collection.documents.append(
        _sample_link(
            "https://www.airbnb.com/rooms/123456789?check_in=2026-04-10",
            platform="airbnb",
            hostname="www.airbnb.com",
        ).model_dump(mode="python")
        | {
            "resolved_url": "https://www.airbnb.com/rooms/123456789?check_in=2026-04-10",
            "resolved_hostname": "www.airbnb.com",
        }
    )

    duplicate = repository.find_duplicate(
        ["https://airbnb.com/rooms/123456789"],
        source_type="group",
        group_id="Cgroup123",
    )

    assert duplicate is not None
    assert duplicate.url == "https://www.airbnb.com/rooms/123456789?check_in=2026-04-10"


def test_mongo_captured_link_repository_isolates_duplicates_by_trip() -> None:
    collection = FakeCollection()
    repository = MongoCapturedLinkRepository(collection)
    collection.documents.extend(
        [
            _sample_link("https://www.booking.com/hotel/jp/foo.html")
            .model_copy(update={"trip_id": "trip-a", "trip_title": "Trip A"})
            .model_dump(mode="python"),
            _sample_link("https://www.booking.com/hotel/jp/foo.html")
            .model_copy(update={"trip_id": "trip-b", "trip_title": "Trip B"})
            .model_dump(mode="python"),
        ]
    )

    duplicate = repository.find_duplicate(
        ["https://www.booking.com/hotel/jp/foo.html"],
        source_type="group",
        trip_id="trip-b",
        group_id="Cgroup123",
    )

    assert duplicate is not None
    assert duplicate.trip_id == "trip-b"


def test_mongo_captured_link_repository_updates_decision_status_with_scope() -> None:
    collection = FakeCollection()
    repository = MongoCapturedLinkRepository(collection)
    collection.documents.append(
        _sample_link("https://www.booking.com/hotel/jp/foo.html")
        .model_copy(update={"trip_id": "trip-a", "trip_title": "Trip A"})
        .model_dump(mode="python")
        | {"_id": "doc-1"}
    )

    updated = repository.update_decision_status(
        "doc-1",
        decision_status="booked",
        source_type="group",
        trip_id="trip-a",
        group_id="Cgroup123",
        updated_by_user_id="Uuser123",
    )

    assert updated is not None
    assert updated.decision_status == "booked"
    assert updated.decision_updated_at is not None
    assert updated.decision_updated_by_user_id == "Uuser123"
    assert updated.notion_sync_status == "pending"


def test_mongo_captured_link_repository_rejects_decision_update_outside_scope() -> None:
    collection = FakeCollection()
    repository = MongoCapturedLinkRepository(collection)
    collection.documents.append(
        _sample_link("https://www.booking.com/hotel/jp/foo.html")
        .model_copy(update={"trip_id": "trip-a", "trip_title": "Trip A"})
        .model_dump(mode="python")
        | {"_id": "doc-1"}
    )

    updated = repository.update_decision_status(
        "doc-1",
        decision_status="booked",
        source_type="group",
        trip_id="trip-other",
        group_id="Cgroup123",
        updated_by_user_id="Uuser123",
    )

    assert updated is None
    assert collection.documents[0]["decision_status"] == "candidate"


def test_create_collector_uses_mongo_backend() -> None:
    created_clients: list[FakeMongoClient] = []

    def fake_factory(uri: str, tz_aware: bool = False) -> FakeMongoClient:
        client = FakeMongoClient(uri, tz_aware=tz_aware)
        created_clients.append(client)
        return client

    settings = Settings(
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


def test_storage_target_redacts_password() -> None:
    settings = Settings(
        mongo_uri="mongodb://line-bot:super-secret@mongo:27017",
        mongo_database="nihon_line_bot",
        mongo_collection="captured_links",
    )

    assert (
        settings.storage_target
        == "mongodb://line-bot:***@mongo:27017/nihon_line_bot.captured_links"
    )
