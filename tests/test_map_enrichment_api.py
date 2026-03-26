from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.map_enrichment.models import (
    EnrichedLodgingMap,
    MapEnrichmentCandidate,
    MapEnrichmentDocument,
)


class DummyCollector:
    def append_many(self, items) -> int:
        return len(items)


class InMemoryMapEnrichmentRepository:
    def __init__(self) -> None:
        self.documents: dict[str, MapEnrichmentDocument] = {
            "doc-pending": MapEnrichmentDocument(
                document_id="doc-pending",
                url="https://short.example/1",
                resolved_url="https://www.booking.com/hotel/jp/resol.html",
                map_status="pending",
                captured_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            ),
            "doc-resolved": MapEnrichmentDocument(
                document_id="doc-resolved",
                url="https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
                resolved_url="https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
                map_status="resolved",
                map_source="structured_data_geo",
                property_name="Existing Hotel",
                google_maps_url="https://www.google.com/maps/search/?api=1&query=foo",
                map_retry_count=0,
                captured_at=datetime(2026, 3, 24, tzinfo=timezone.utc),
            ),
        }

    def find_pending(self, limit: int):
        candidates: list[MapEnrichmentCandidate] = []
        for document in self.documents.values():
            if document.map_status == "pending":
                candidates.append(
                    MapEnrichmentCandidate(
                        document_id=document.document_id,
                        url=document.url,
                        resolved_url=document.resolved_url,
                    )
                )
        return candidates[:limit]

    def find_by_document_id(self, document_id: str):
        document = self.documents.get(document_id)
        if document is None:
            return None
        return MapEnrichmentCandidate(
            document_id=document.document_id,
            url=document.url,
            resolved_url=document.resolved_url,
        )

    def list_documents(self, limit: int, statuses=None):
        items = list(self.documents.values())
        if statuses:
            items = [item for item in items if item.map_status in statuses]
        items.sort(key=lambda item: item.captured_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:limit]

    def mark_resolved(self, document_id: str, enrichment: EnrichedLodgingMap) -> None:
        current = self.documents[document_id]
        self.documents[document_id] = MapEnrichmentDocument(
            document_id=current.document_id,
            url=current.url,
            resolved_url=enrichment.resolved_url or current.resolved_url,
            map_status="resolved",
            map_source=enrichment.map_source,
            property_name=enrichment.property_name,
            formatted_address=enrichment.formatted_address,
            latitude=enrichment.latitude,
            longitude=enrichment.longitude,
            google_maps_url=enrichment.google_maps_url,
            map_error=None,
            map_retry_count=0,
            captured_at=current.captured_at,
        )

    def mark_failed(self, document_id: str, error: str) -> None:
        current = self.documents[document_id]
        self.documents[document_id] = MapEnrichmentDocument(
            document_id=current.document_id,
            url=current.url,
            resolved_url=current.resolved_url,
            map_status="failed",
            map_source=current.map_source,
            property_name=current.property_name,
            formatted_address=current.formatted_address,
            latitude=current.latitude,
            longitude=current.longitude,
            google_maps_url=current.google_maps_url,
            map_error=error,
            map_retry_count=current.map_retry_count + 1,
            captured_at=current.captured_at,
        )


class FakeMapEnrichmentService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def enrich(self, url: str) -> EnrichedLodgingMap | None:
        self.calls.append(url)
        return EnrichedLodgingMap(
            property_name="Hotel Resol Ueno",
            formatted_address="7-2-9 Ueno, Taito City, Tokyo, JP",
            latitude=35.712345,
            longitude=139.778901,
            google_maps_url=(
                "https://www.google.com/maps/search/?api=1"
                "&query=35.712345%2C139.778901"
            ),
            map_source="structured_data_geo",
        )


def test_map_enrichment_documents_endpoint_lists_mongo_like_documents() -> None:
    repository = InMemoryMapEnrichmentRepository()
    client = TestClient(
        create_app(
            settings=Settings(),
            collector=DummyCollector(),
            map_enrichment_repository=repository,
            map_enrichment_service=FakeMapEnrichmentService(),
        )
    )

    response = client.get("/jobs/map-enrichment/documents", params={"limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["is_success"] is True
    assert body["message"] == "Fetched map enrichment documents."
    assert body["data"]["count"] == 2
    assert body["data"]["documents"][0]["document_id"] == "doc-pending"
    assert body["data"]["documents"][0]["map_status"] == "pending"
    assert body["data"]["documents"][1]["document_id"] == "doc-resolved"


def test_map_enrichment_run_endpoint_processes_pending_documents() -> None:
    repository = InMemoryMapEnrichmentRepository()
    service = FakeMapEnrichmentService()
    client = TestClient(
        create_app(
            settings=Settings(),
            collector=DummyCollector(),
            map_enrichment_repository=repository,
            map_enrichment_service=service,
        )
    )

    response = client.post("/jobs/map-enrichment/run", json={"limit": 5})

    assert response.status_code == 200
    assert response.json() == {
        "is_success": True,
        "message": "Map enrichment job finished.",
        "data": {
            "processed": 1,
            "resolved": 1,
            "failed": 0,
            "limit_used": 5,
        },
    }
    assert service.calls == ["https://www.booking.com/hotel/jp/resol.html"]

    documents_response = client.get(
        "/jobs/map-enrichment/documents",
        params={"status": "resolved", "limit": 10},
    )
    documents = documents_response.json()["data"]["documents"]
    pending_document = next(
        item for item in documents if item["document_id"] == "doc-pending"
    )
    assert pending_document["map_status"] == "resolved"
    assert pending_document["property_name"] == "Hotel Resol Ueno"
    assert pending_document["google_maps_url"] is not None


def test_map_enrichment_retry_endpoint_processes_single_document() -> None:
    repository = InMemoryMapEnrichmentRepository()
    failed_document = repository.documents["doc-pending"]
    repository.documents["doc-pending"] = MapEnrichmentDocument(
        document_id=failed_document.document_id,
        url=failed_document.url,
        resolved_url=failed_document.resolved_url,
        map_status="failed",
        map_error="No map metadata could be extracted from lodging page.",
        map_retry_count=1,
        captured_at=failed_document.captured_at,
    )
    service = FakeMapEnrichmentService()
    client = TestClient(
        create_app(
            settings=Settings(),
            collector=DummyCollector(),
            map_enrichment_repository=repository,
            map_enrichment_service=service,
        )
    )

    response = client.post("/jobs/map-enrichment/documents/doc-pending/retry")

    assert response.status_code == 200
    assert response.json() == {
        "is_success": True,
        "message": "Map enrichment retry finished.",
        "data": {
            "document_id": "doc-pending",
            "processed": 1,
            "resolved": 1,
            "failed": 0,
        },
    }
    assert service.calls == ["https://www.booking.com/hotel/jp/resol.html"]
    assert repository.documents["doc-pending"].map_status == "resolved"
