from __future__ import annotations

from typing import Any
from pathlib import Path
from typing import Protocol, Sequence

from app.models import CapturedLodgingLink


class CapturedLinkRepository(Protocol):
    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int: ...


class InsertManyResult(Protocol):
    inserted_ids: Sequence[Any]


class MongoCollection(Protocol):
    def insert_many(
        self,
        documents: list[dict[str, Any]],
        ordered: bool = True,
    ) -> InsertManyResult: ...


class JsonlCapturedLinkRepository:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        if not items:
            return 0

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as output_file:
            for item in items:
                output_file.write(item.model_dump_json() + "\n")
        return len(items)


class MongoCapturedLinkRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        if not items:
            return 0

        documents = [item.model_dump(mode="python") for item in items]
        result = self.collection.insert_many(documents, ordered=True)
        return len(result.inserted_ids)
