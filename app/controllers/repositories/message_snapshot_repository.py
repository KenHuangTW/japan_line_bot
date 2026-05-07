from __future__ import annotations

from typing import Protocol

from app.models import LineMessageSnapshot


class MessageSnapshotRepository(Protocol):
    def save(self, snapshot: LineMessageSnapshot) -> None: ...

    def find_text_by_message_id(
        self,
        message_id: str,
        *,
        source_type: str,
        group_id: str | None = None,
        room_id: str | None = None,
        user_id: str | None = None,
    ) -> LineMessageSnapshot | None: ...
