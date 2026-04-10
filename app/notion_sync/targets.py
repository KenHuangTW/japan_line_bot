from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from app.notion_sync.models import (
    NotionDatabaseTarget,
    NotionSyncCandidate,
    NotionSyncSourceScope,
)
from app.notion_sync.service import (
    DEFAULT_NOTION_DATABASE_TITLE,
    NotionLodgingSyncService,
)

TargetSource = Literal["default", "scoped"]


@dataclass(frozen=True)
class NotionTargetConfig:
    source_type: str | None = None
    group_id: str | None = None
    room_id: str | None = None
    user_id: str | None = None
    parent_page_id: str | None = None
    database_id: str = ""
    data_source_id: str = ""
    database_title: str | None = None
    database_url: str | None = None
    public_database_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_type", _normalize_optional(self.source_type))
        object.__setattr__(self, "group_id", _normalize_optional(self.group_id))
        object.__setattr__(self, "room_id", _normalize_optional(self.room_id))
        object.__setattr__(self, "user_id", _normalize_optional(self.user_id))
        object.__setattr__(
            self,
            "parent_page_id",
            _normalize_optional(self.parent_page_id),
        )
        object.__setattr__(self, "database_id", _normalize_required(self.database_id))
        object.__setattr__(
            self,
            "data_source_id",
            _normalize_required(self.data_source_id),
        )
        object.__setattr__(
            self,
            "database_title",
            _normalize_optional(self.database_title),
        )
        object.__setattr__(
            self,
            "database_url",
            _normalize_optional(self.database_url),
        )
        object.__setattr__(
            self,
            "public_database_url",
            _normalize_optional(self.public_database_url),
        )

    @classmethod
    def from_source_scope(
        cls,
        source_scope: NotionSyncSourceScope,
        *,
        parent_page_id: str | None = None,
        database_id: str = "",
        data_source_id: str = "",
        database_title: str | None = None,
        database_url: str | None = None,
        public_database_url: str | None = None,
    ) -> "NotionTargetConfig":
        return cls(
            source_type=source_scope.source_type,
            group_id=source_scope.group_id,
            room_id=source_scope.room_id,
            user_id=source_scope.user_id,
            parent_page_id=parent_page_id,
            database_id=database_id,
            data_source_id=data_source_id,
            database_title=database_title,
            database_url=database_url,
            public_database_url=public_database_url,
        )

    @property
    def source_scope(self) -> NotionSyncSourceScope | None:
        return build_source_scope(
            source_type=self.source_type,
            group_id=self.group_id,
            room_id=self.room_id,
            user_id=self.user_id,
        )

    @property
    def is_setup_configured(self) -> bool:
        return bool(self.parent_page_id or self.data_source_id)

    @property
    def is_sync_configured(self) -> bool:
        return bool(self.data_source_id)

    @property
    def share_url(self) -> str | None:
        return self.public_database_url or self.database_url or None

    def with_database_target(
        self,
        target: NotionDatabaseTarget,
    ) -> "NotionTargetConfig":
        return NotionTargetConfig(
            source_type=self.source_type,
            group_id=self.group_id,
            room_id=self.room_id,
            user_id=self.user_id,
            parent_page_id=self.parent_page_id,
            database_id=target.database_id,
            data_source_id=target.data_source_id,
            database_title=target.title or self.database_title,
            database_url=target.url,
            public_database_url=target.public_url,
        )


@dataclass(frozen=True)
class ResolvedNotionService:
    service: NotionLodgingSyncService
    target: NotionTargetConfig
    target_source: TargetSource
    requested_source_scope: NotionSyncSourceScope | None = None


class MongoCollection(Protocol):
    def find_one(
        self,
        filter: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None: ...

    def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any: ...


class NotionTargetRepository(Protocol):
    def find_by_source_scope(
        self,
        source_scope: NotionSyncSourceScope,
    ) -> NotionTargetConfig | None: ...

    def save(self, target: NotionTargetConfig) -> None: ...


class MongoNotionTargetRepository:
    def __init__(self, collection: MongoCollection) -> None:
        self.collection = collection

    def find_by_source_scope(
        self,
        source_scope: NotionSyncSourceScope,
    ) -> NotionTargetConfig | None:
        document = self.collection.find_one(_build_source_scope_query(source_scope))
        if document is None:
            return None
        return NotionTargetConfig(
            source_type=document.get("source_type"),
            group_id=document.get("group_id"),
            room_id=document.get("room_id"),
            user_id=document.get("user_id"),
            parent_page_id=document.get("parent_page_id"),
            database_id=document.get("database_id", ""),
            data_source_id=document.get("data_source_id", ""),
            database_title=document.get("database_title"),
            database_url=document.get("database_url"),
            public_database_url=document.get("public_database_url"),
        )

    def save(self, target: NotionTargetConfig) -> None:
        source_scope = target.source_scope
        if source_scope is None:
            raise ValueError("Scoped Notion targets require a source scope.")

        now = datetime.now(timezone.utc)
        self.collection.update_one(
            _build_source_scope_query(source_scope),
            {
                "$set": {
                    "source_type": source_scope.source_type,
                    "group_id": source_scope.group_id,
                    "room_id": source_scope.room_id,
                    "user_id": source_scope.user_id,
                    "parent_page_id": target.parent_page_id,
                    "database_id": target.database_id or None,
                    "data_source_id": target.data_source_id or None,
                    "database_title": target.database_title,
                    "database_url": target.database_url,
                    "public_database_url": target.public_database_url,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )


class NotionTargetManager:
    def __init__(
        self,
        default_service: NotionLodgingSyncService | None,
        target_repository: NotionTargetRepository | None = None,
    ) -> None:
        self.default_service = default_service
        self.target_repository = target_repository

    def resolve_target(
        self,
        source_scope: NotionSyncSourceScope | None,
    ) -> tuple[NotionTargetConfig, TargetSource] | None:
        if source_scope is not None and self.target_repository is not None:
            target = self.target_repository.find_by_source_scope(source_scope)
            if target is not None and target.is_setup_configured:
                return target, "scoped"

        default_target = self.default_target
        if default_target is not None and default_target.is_setup_configured:
            return default_target, "default"
        return None

    def resolve_service(
        self,
        source_scope: NotionSyncSourceScope | None,
    ) -> ResolvedNotionService | None:
        resolved = self.resolve_target(source_scope)
        if resolved is None or self.default_service is None:
            return None

        target, target_source = resolved
        service = (
            self.default_service
            if target_source == "default"
            else self.default_service.clone_with_target(
                parent_page_id=target.parent_page_id or "",
                database_id=target.database_id,
                data_source_id=target.data_source_id,
                database_title=target.database_title
                or self.default_service.database_title
                or DEFAULT_NOTION_DATABASE_TITLE,
                database_url=target.database_url or "",
                public_database_url=target.public_database_url or "",
            )
        )
        return ResolvedNotionService(
            service=service,
            target=target,
            target_source=target_source,
            requested_source_scope=source_scope,
        )

    def resolve_service_for_candidate(
        self,
        candidate: NotionSyncCandidate,
    ) -> ResolvedNotionService | None:
        return self.resolve_service(source_scope_from_candidate(candidate))

    async def setup_database(
        self,
        *,
        title: str | None = None,
        source_scope: NotionSyncSourceScope | None = None,
        parent_page_id: str | None = None,
        data_source_id: str | None = None,
    ) -> ResolvedNotionService | None:
        resolved_service = self._build_setup_service(
            source_scope=source_scope,
            parent_page_id=parent_page_id,
            data_source_id=data_source_id,
        )
        if resolved_service is None:
            return None

        target = await resolved_service.service.setup_database(title=title)
        updated_target = resolved_service.target.with_database_target(target)
        updated_resolved = ResolvedNotionService(
            service=resolved_service.service,
            target=updated_target,
            target_source=resolved_service.target_source,
            requested_source_scope=resolved_service.requested_source_scope,
        )
        if (
            updated_resolved.target_source == "scoped"
            and self.target_repository is not None
        ):
            self.target_repository.save(updated_target)
        return updated_resolved

    @property
    def default_target(self) -> NotionTargetConfig | None:
        if self.default_service is None:
            return None
        return NotionTargetConfig(
            parent_page_id=self.default_service.parent_page_id,
            database_id=self.default_service.database_id,
            data_source_id=self.default_service.data_source_id,
            database_title=self.default_service.database_title,
            database_url=self.default_service.database_url,
            public_database_url=self.default_service.public_database_url,
        )

    def _build_setup_service(
        self,
        *,
        source_scope: NotionSyncSourceScope | None,
        parent_page_id: str | None = None,
        data_source_id: str | None = None,
    ) -> ResolvedNotionService | None:
        if self.default_service is None:
            return None

        if source_scope is None:
            default_target = self.default_target
            if default_target is None or not default_target.is_setup_configured:
                return None
            return ResolvedNotionService(
                service=self.default_service,
                target=default_target,
                target_source="default",
                requested_source_scope=None,
            )

        if self.target_repository is None:
            return None

        existing_target = self.target_repository.find_by_source_scope(source_scope)
        target = _build_setup_target(
            source_scope=source_scope,
            existing_target=existing_target,
            parent_page_id=parent_page_id,
            data_source_id=data_source_id,
            default_title=self.default_service.database_title,
        )
        if not target.is_setup_configured:
            return None

        return ResolvedNotionService(
            service=self.default_service.clone_with_target(
                parent_page_id=target.parent_page_id or "",
                database_id=target.database_id,
                data_source_id=target.data_source_id,
                database_title=target.database_title
                or self.default_service.database_title
                or DEFAULT_NOTION_DATABASE_TITLE,
                database_url=target.database_url or "",
                public_database_url=target.public_database_url or "",
            ),
            target=target,
            target_source="scoped",
            requested_source_scope=source_scope,
        )


def build_source_scope(
    *,
    source_type: str | None = None,
    group_id: str | None = None,
    room_id: str | None = None,
    user_id: str | None = None,
) -> NotionSyncSourceScope | None:
    normalized_source_type = _normalize_optional(source_type)
    normalized_group_id = _normalize_optional(group_id)
    normalized_room_id = _normalize_optional(room_id)
    normalized_user_id = _normalize_optional(user_id)

    if (
        normalized_source_type is None
        and normalized_group_id is None
        and normalized_room_id is None
        and normalized_user_id is None
    ):
        return None

    if normalized_source_type is None:
        raise ValueError("source_type is required when source scope ids are provided.")

    if normalized_source_type == "group":
        if normalized_group_id is None:
            raise ValueError("group_id is required when source_type=group.")
        return NotionSyncSourceScope(
            source_type="group",
            group_id=normalized_group_id,
        )

    if normalized_source_type == "room":
        if normalized_room_id is None:
            raise ValueError("room_id is required when source_type=room.")
        return NotionSyncSourceScope(
            source_type="room",
            room_id=normalized_room_id,
        )

    if normalized_source_type == "user":
        if normalized_user_id is None:
            raise ValueError("user_id is required when source_type=user.")
        return NotionSyncSourceScope(
            source_type="user",
            user_id=normalized_user_id,
        )

    raise ValueError("source_type must be one of group, room, or user.")


def source_scope_from_candidate(
    candidate: NotionSyncCandidate,
) -> NotionSyncSourceScope | None:
    return build_source_scope(
        source_type=candidate.source_type,
        group_id=candidate.group_id,
        room_id=candidate.room_id,
        user_id=candidate.user_id,
    )


def source_scope_to_fields(
    source_scope: NotionSyncSourceScope | None,
) -> dict[str, str | None]:
    if source_scope is None:
        return {
            "source_type": None,
            "group_id": None,
            "room_id": None,
            "user_id": None,
        }
    return {
        "source_type": source_scope.source_type,
        "group_id": source_scope.group_id,
        "room_id": source_scope.room_id,
        "user_id": source_scope.user_id,
    }


def _build_setup_target(
    *,
    source_scope: NotionSyncSourceScope,
    existing_target: NotionTargetConfig | None,
    parent_page_id: str | None,
    data_source_id: str | None,
    default_title: str,
) -> NotionTargetConfig:
    normalized_parent_page_id = _normalize_optional(parent_page_id)
    normalized_data_source_id = _normalize_required(data_source_id)

    if normalized_data_source_id:
        if (
            existing_target is not None
            and existing_target.data_source_id == normalized_data_source_id
            and normalized_parent_page_id is None
        ):
            return existing_target
        return NotionTargetConfig.from_source_scope(
            source_scope,
            parent_page_id=normalized_parent_page_id
            or (existing_target.parent_page_id if existing_target is not None else None),
            data_source_id=normalized_data_source_id,
            database_title=(
                existing_target.database_title if existing_target is not None else None
            )
            or default_title,
        )

    if normalized_parent_page_id is not None:
        if (
            existing_target is not None
            and existing_target.parent_page_id == normalized_parent_page_id
            and not existing_target.data_source_id
        ):
            return existing_target
        return NotionTargetConfig.from_source_scope(
            source_scope,
            parent_page_id=normalized_parent_page_id,
            database_title=(
                existing_target.database_title if existing_target is not None else None
            )
            or default_title,
        )

    if existing_target is not None:
        return existing_target

    return NotionTargetConfig.from_source_scope(
        source_scope,
        database_title=default_title,
    )


def _build_source_scope_query(
    source_scope: NotionSyncSourceScope,
) -> dict[str, Any]:
    query: dict[str, Any] = {"source_type": source_scope.source_type}
    if source_scope.source_type == "group":
        query["group_id"] = source_scope.group_id
    elif source_scope.source_type == "room":
        query["room_id"] = source_scope.room_id
    elif source_scope.source_type == "user":
        query["user_id"] = source_scope.user_id
    return query


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_required(value: str | None) -> str:
    return _normalize_optional(value) or ""
