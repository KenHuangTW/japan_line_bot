from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

from app.models import CapturedLodgingLink


class Collector(Protocol):
    def append_many(self, items: Sequence[CapturedLodgingLink]) -> int:
        ...


class JsonlCollector:
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
