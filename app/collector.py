from __future__ import annotations

from typing import Any, Callable, Protocol

from app.config import Settings
from app.controllers.repositories.captured_link_repository import (
    CapturedLinkRepository,
    JsonlCapturedLinkRepository,
    MongoCapturedLinkRepository,
)

Collector = CapturedLinkRepository
JsonlCollector = JsonlCapturedLinkRepository
MongoCollector = MongoCapturedLinkRepository


class MongoDatabaseLike(Protocol):
    def __getitem__(self, name: str) -> Any: ...


class MongoClientLike(Protocol):
    def __getitem__(self, name: str) -> MongoDatabaseLike: ...

    def close(self) -> None: ...


class MissingMongoDependencyCollector:
    def __init__(self, error: ModuleNotFoundError) -> None:
        self.error = error

    def append_many(self, items) -> int:
        raise RuntimeError(
            "pymongo is required when STORAGE_BACKEND=mongo. "
            "Install project dependencies before capturing links."
        ) from self.error


MongoClientFactory = Callable[..., MongoClientLike]


def create_collector(
    settings: Settings,
    mongo_client_factory: MongoClientFactory | None = None,
) -> tuple[Collector, MongoClientLike | None]:
    if settings.storage_backend == "jsonl":
        return JsonlCollector(settings.collector_output_path), None

    active_factory = mongo_client_factory
    if active_factory is None:
        try:
            from pymongo import MongoClient
        except ModuleNotFoundError as error:
            return MissingMongoDependencyCollector(error), None
        active_factory = MongoClient

    mongo_client = active_factory(settings.mongo_uri, tz_aware=True)
    collection = mongo_client[settings.mongo_database][settings.mongo_collection]
    return MongoCollector(collection), mongo_client


__all__ = [
    "Collector",
    "JsonlCollector",
    "MongoCollector",
    "create_collector",
]
