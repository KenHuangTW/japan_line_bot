from __future__ import annotations

from typing import Any, Protocol, Sequence

from app.models import CapturedLodgingLink


class InsertManyResult(Protocol):
    inserted_ids: Sequence[Any]


class MongoCollection(Protocol):
    def insert_many(
        self,
        documents: list[dict[str, Any]],
        ordered: bool = True,
    ) -> InsertManyResult: ...


class MongoCapturedLinkRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        if not items:
            return 0

        documents = [item.model_dump(mode="python") for item in items]
        result = self.collection.insert_many(documents, ordered=True)
        return len(result.inserted_ids)
