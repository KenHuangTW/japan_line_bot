from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceScope:
    source_type: str
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    trip_id: str | None = None
    trip_title: str | None = None


def build_source_scope(
    source_type: str | None = None,
    group_id: str | None = None,
    room_id: str | None = None,
    user_id: str | None = None,
    trip_id: str | None = None,
    trip_title: str | None = None,
) -> SourceScope | None:
    normalized_source_type = _normalize_optional(source_type)
    normalized_group_id = _normalize_optional(group_id)
    normalized_room_id = _normalize_optional(room_id)
    normalized_user_id = _normalize_optional(user_id)
    normalized_trip_id = _normalize_optional(trip_id)
    normalized_trip_title = _normalize_optional(trip_title)

    if (
        normalized_source_type is None
        and normalized_group_id is None
        and normalized_room_id is None
        and normalized_user_id is None
        and normalized_trip_id is None
        and normalized_trip_title is None
    ):
        return None

    if normalized_source_type is None:
        raise ValueError("source_type is required when source scope ids are provided.")

    if normalized_source_type == "group":
        if normalized_group_id is None:
            raise ValueError("group_id is required when source_type=group.")
        return SourceScope(
            source_type="group",
            group_id=normalized_group_id,
            trip_id=normalized_trip_id,
            trip_title=normalized_trip_title,
        )

    if normalized_source_type == "room":
        if normalized_room_id is None:
            raise ValueError("room_id is required when source_type=room.")
        return SourceScope(
            source_type="room",
            room_id=normalized_room_id,
            trip_id=normalized_trip_id,
            trip_title=normalized_trip_title,
        )

    if normalized_source_type == "user":
        if normalized_user_id is None:
            raise ValueError("user_id is required when source_type=user.")
        return SourceScope(
            source_type="user",
            user_id=normalized_user_id,
            trip_id=normalized_trip_id,
            trip_title=normalized_trip_title,
        )

    raise ValueError("source_type must be one of group, room, or user.")


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
