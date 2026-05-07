from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.controllers.repositories.mongo_message_snapshot_repository import (
    MongoMessageSnapshotRepository,
)
from app.models import build_line_message_snapshot


class FakeUpdateOneResult:
    def __init__(self, matched_count: int = 1) -> None:
        self.matched_count = matched_count


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> FakeUpdateOneResult:
        for index, document in enumerate(self.documents):
            if _matches(document, filter):
                updated = dict(document)
                updated.update(update.get("$set", {}))
                self.documents[index] = updated
                return FakeUpdateOneResult()
        if kwargs.get("upsert"):
            self.documents.append(dict(update.get("$set", {})))
        return FakeUpdateOneResult(0)

    def find_one(self, filter: dict[str, Any], *args: Any, **kwargs: Any):
        for document in self.documents:
            if _matches(document, filter):
                return dict(document)
        return None


def test_mongo_message_snapshot_repository_saves_and_reads_scoped_text() -> None:
    collection = FakeCollection()
    repository = MongoMessageSnapshotRepository(collection)
    snapshot = build_line_message_snapshot(
        message_id="msg-1",
        source_type="group",
        group_id="Cgroup",
        user_id="Utarget",
        sender_user_id="Usender",
        message_text="## 第 1 天 — 2026-06-01",
        quote_token="quote-token",
        event_timestamp_ms=1711111111111,
        retention_days=7,
    )

    repository.save(snapshot)
    found = repository.find_text_by_message_id(
        "msg-1",
        source_type="group",
        group_id="Cgroup",
        user_id="Utarget",
    )

    assert found is not None
    assert found.message_text == "## 第 1 天 — 2026-06-01"
    assert found.quote_token == "quote-token"
    assert found.expires_at is not None


def test_mongo_message_snapshot_repository_enforces_scope_and_expiry() -> None:
    collection = FakeCollection()
    repository = MongoMessageSnapshotRepository(collection)
    snapshot = build_line_message_snapshot(
        message_id="msg-1",
        source_type="group",
        group_id="Cgroup",
        message_text="行程",
    )
    expired = snapshot.model_copy(
        update={"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}
    )
    repository.save(expired)

    assert (
        repository.find_text_by_message_id(
            "msg-1",
            source_type="group",
            group_id="Cother",
        )
        is None
    )
    assert (
        repository.find_text_by_message_id(
            "msg-1",
            source_type="group",
            group_id="Cgroup",
        )
        is None
    )


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(document, clause) for clause in value):
                return False
            continue
        if isinstance(value, dict) and "$gt" in value:
            document_value = document.get(key)
            if document_value is None or not document_value > value["$gt"]:
                return False
            continue
        if document.get(key) != value:
            return False
    return True
