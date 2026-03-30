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
                details_status="pending",
                pricing_status="pending",
                captured_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            ),
            "doc-resolved": MapEnrichmentDocument(
                document_id="doc-resolved",
                url="https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
                resolved_url="https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
                map_status="resolved",
                map_source="structured_data_geo",
                details_status="resolved",
                details_source="structured_data_details",
                pricing_status="resolved",
                pricing_source="structured_data_offer",
                property_name="Existing Hotel",
                property_type="hotel",
                amenities=("Free WiFi",),
                price_amount=22000,
                price_currency="JPY",
                is_sold_out=False,
                availability_source="agoda_secondary_data_room_grid",
                google_maps_url="https://www.google.com/maps/search/?api=1&query=foo",
                google_maps_search_url="https://www.google.com/maps/search/?api=1&query=foo",
                map_retry_count=0,
                captured_at=datetime(2026, 3, 24, tzinfo=timezone.utc),
            ),
            "doc-failed": MapEnrichmentDocument(
                document_id="doc-failed",
                url="https://www.booking.com/hotel/jp/failed.html",
                resolved_url="https://www.booking.com/hotel/jp/failed.html",
                map_status="failed",
                details_status="failed",
                pricing_status="failed",
                map_error="simulated old failure",
                map_retry_count=2,
                details_error="simulated old failure",
                details_retry_count=2,
                pricing_error="simulated old failure",
                pricing_retry_count=2,
                captured_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
            ),
        }

    def find_pending(self, limit: int | None, source_scope=None):
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
        if limit is None:
            return candidates
        return candidates[:limit]

    def find_all(self, limit: int | None = None, source_scope=None):
        items = sorted(
            self.documents.values(),
            key=lambda item: item.captured_at or datetime.min.replace(tzinfo=timezone.utc),
        )
        candidates = [
            MapEnrichmentCandidate(
                document_id=document.document_id,
                url=document.url,
                resolved_url=document.resolved_url,
            )
            for document in items
        ]
        if limit is None:
            return candidates
        return candidates[:limit]

    def find_failed(self, limit: int, source_scope=None):
        candidates: list[MapEnrichmentCandidate] = []
        for document in self.documents.values():
            if document.map_status == "failed":
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
            map_status="resolved" if enrichment.has_coordinates else "partial",
            map_source=enrichment.map_source,
            details_status="resolved" if enrichment.has_details else "partial",
            details_source=enrichment.details_source,
            pricing_status="resolved" if enrichment.has_pricing else "partial",
            pricing_source=enrichment.pricing_source,
            property_name=enrichment.property_name,
            formatted_address=enrichment.formatted_address,
            street_address=enrichment.street_address,
            district=enrichment.district,
            city=enrichment.city,
            region=enrichment.region,
            postal_code=enrichment.postal_code,
            country_name=enrichment.country_name,
            country_code=enrichment.country_code,
            latitude=enrichment.latitude,
            longitude=enrichment.longitude,
            property_type=enrichment.property_type,
            room_count=enrichment.room_count,
            bedroom_count=enrichment.bedroom_count,
            bathroom_count=enrichment.bathroom_count,
            amenities=enrichment.amenities,
            price_amount=enrichment.price_amount,
            price_currency=enrichment.price_currency,
            source_price_amount=enrichment.source_price_amount,
            source_price_currency=enrichment.source_price_currency,
            price_exchange_rate=enrichment.price_exchange_rate,
            price_exchange_rate_source=enrichment.price_exchange_rate_source,
            is_sold_out=enrichment.is_sold_out,
            availability_source=enrichment.availability_source,
            google_maps_url=enrichment.google_maps_url,
            google_maps_search_url=enrichment.google_maps_search_url,
            map_error=None,
            map_retry_count=0,
            details_error=None,
            details_retry_count=0,
            pricing_error=None,
            pricing_retry_count=0,
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
            details_status="failed",
            details_source=current.details_source,
            pricing_status="failed",
            pricing_source=current.pricing_source,
            property_name=current.property_name,
            formatted_address=current.formatted_address,
            street_address=current.street_address,
            district=current.district,
            city=current.city,
            region=current.region,
            postal_code=current.postal_code,
            country_name=current.country_name,
            country_code=current.country_code,
            latitude=current.latitude,
            longitude=current.longitude,
            property_type=current.property_type,
            room_count=current.room_count,
            bedroom_count=current.bedroom_count,
            bathroom_count=current.bathroom_count,
            amenities=current.amenities,
            price_amount=current.price_amount,
            price_currency=current.price_currency,
            source_price_amount=current.source_price_amount,
            source_price_currency=current.source_price_currency,
            price_exchange_rate=current.price_exchange_rate,
            price_exchange_rate_source=current.price_exchange_rate_source,
            is_sold_out=current.is_sold_out,
            availability_source=current.availability_source,
            google_maps_url=current.google_maps_url,
            google_maps_search_url=current.google_maps_search_url,
            map_error=error,
            map_retry_count=current.map_retry_count + 1,
            details_error=error,
            details_retry_count=current.details_retry_count + 1,
            pricing_error=error,
            pricing_retry_count=current.pricing_retry_count + 1,
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
            street_address="7-2-9 Ueno",
            district="Taito City",
            city="Tokyo",
            region="Tokyo",
            postal_code="110-0005",
            country_name="Japan",
            country_code="JP",
            latitude=35.712345,
            longitude=139.778901,
            property_type="hotel",
            bedroom_count=1,
            bathroom_count=1,
            amenities=("Free WiFi", "Non-smoking rooms"),
            details_source="structured_data_details",
            price_amount=18000,
            price_currency="JPY",
            pricing_source="structured_data_offer",
            google_maps_url=(
                "https://www.google.com/maps/search/?api=1"
                "&query=35.712345%2C139.778901"
            ),
            google_maps_search_url=(
                "https://www.google.com/maps/search/?api=1"
                "&query=7-2-9+Ueno%2C+Taito+City%2C+Tokyo%2C+JP"
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
    assert body["message"] == "Fetched lodging enrichment documents."
    assert body["data"]["count"] == 3
    assert body["data"]["documents"][0]["document_id"] == "doc-pending"
    assert body["data"]["documents"][0]["map_status"] == "pending"
    assert body["data"]["documents"][1]["document_id"] == "doc-resolved"
    assert body["data"]["documents"][1]["details_status"] == "resolved"
    assert body["data"]["documents"][1]["pricing_status"] == "resolved"
    assert body["data"]["documents"][1]["amenities"] == ["Free WiFi"]
    assert body["data"]["documents"][1]["is_sold_out"] is False
    assert (
        body["data"]["documents"][1]["availability_source"]
        == "agoda_secondary_data_room_grid"
    )


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

    response = client.post("/jobs/lodging-enrichment/run", json={"limit": 5})

    assert response.status_code == 200
    assert response.json() == {
        "is_success": True,
        "message": "Lodging enrichment job finished.",
        "data": {
            "processed": 1,
            "resolved": 1,
            "partial": 0,
            "details_resolved": 1,
            "pricing_resolved": 1,
            "failed": 0,
            "limit_used": 5,
        },
    }
    assert service.calls == ["https://www.booking.com/hotel/jp/resol.html"]

    documents_response = client.get(
        "/jobs/lodging-enrichment/documents",
        params={"status": "resolved", "limit": 10},
    )
    documents = documents_response.json()["data"]["documents"]
    pending_document = next(
        item for item in documents if item["document_id"] == "doc-pending"
    )
    assert pending_document["map_status"] == "resolved"
    assert pending_document["details_status"] == "resolved"
    assert pending_document["pricing_status"] == "resolved"
    assert pending_document["property_name"] == "Hotel Resol Ueno"
    assert pending_document["property_type"] == "hotel"
    assert pending_document["city"] == "Tokyo"
    assert pending_document["price_amount"] == 18000
    assert pending_document["price_currency"] == "JPY"
    assert pending_document["google_maps_url"] is not None
    assert pending_document["google_maps_search_url"] is not None


def test_map_enrichment_retry_endpoint_processes_single_document() -> None:
    repository = InMemoryMapEnrichmentRepository()
    failed_document = repository.documents["doc-pending"]
    repository.documents["doc-pending"] = MapEnrichmentDocument(
        document_id=failed_document.document_id,
        url=failed_document.url,
        resolved_url=failed_document.resolved_url,
        map_status="failed",
        details_status="failed",
        pricing_status="failed",
        map_error="No map metadata could be extracted from lodging page.",
        map_retry_count=1,
        details_error="No map metadata could be extracted from lodging page.",
        details_retry_count=1,
        pricing_error="No map metadata could be extracted from lodging page.",
        pricing_retry_count=1,
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

    response = client.post("/jobs/lodging-enrichment/documents/doc-pending/retry")

    assert response.status_code == 200
    assert response.json() == {
        "is_success": True,
        "message": "Lodging enrichment retry finished.",
        "data": {
            "document_id": "doc-pending",
            "processed": 1,
            "resolved": 1,
            "partial": 0,
            "details_resolved": 1,
            "pricing_resolved": 1,
            "failed": 0,
        },
    }
    assert service.calls == ["https://www.booking.com/hotel/jp/resol.html"]
    assert repository.documents["doc-pending"].map_status == "resolved"
    assert repository.documents["doc-pending"].details_status == "resolved"
    assert repository.documents["doc-pending"].pricing_status == "resolved"


def test_map_enrichment_retry_all_endpoint_processes_all_documents() -> None:
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

    response = client.post("/jobs/lodging-enrichment/documents/retry-all")

    assert response.status_code == 200
    assert response.json() == {
        "is_success": True,
        "message": "Lodging enrichment bulk retry finished.",
        "data": {
            "processed": 3,
            "resolved": 3,
            "partial": 0,
            "details_resolved": 3,
            "pricing_resolved": 3,
            "failed": 0,
            "limit_used": 3,
        },
    }
    assert service.calls == [
        "https://www.booking.com/hotel/jp/failed.html",
        "https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html",
        "https://www.booking.com/hotel/jp/resol.html",
    ]
    assert repository.documents["doc-failed"].map_status == "resolved"
    assert repository.documents["doc-resolved"].map_status == "resolved"
    assert repository.documents["doc-pending"].map_status == "resolved"


class PartialOnlyMapEnrichmentService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def enrich(self, url: str) -> EnrichedLodgingMap | None:
        self.calls.append(url)
        return EnrichedLodgingMap(
            property_name="Hotel Resol Ueno",
            formatted_address="7-2-9 Ueno, Taito City, Tokyo, JP",
            google_maps_search_url=(
                "https://www.google.com/maps/search/?api=1"
                "&query=7-2-9+Ueno%2C+Taito+City%2C+Tokyo%2C+JP"
            ),
            map_source="booking_header_address",
        )


def test_map_enrichment_run_endpoint_returns_partial_for_search_only_results() -> None:
    repository = InMemoryMapEnrichmentRepository()
    service = PartialOnlyMapEnrichmentService()
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
    assert response.json()["data"] == {
        "processed": 1,
        "resolved": 0,
        "partial": 1,
        "details_resolved": 0,
        "pricing_resolved": 0,
        "failed": 0,
        "limit_used": 5,
    }
    assert repository.documents["doc-pending"].map_status == "partial"
    assert repository.documents["doc-pending"].details_status == "partial"
    assert repository.documents["doc-pending"].pricing_status == "partial"
    assert repository.documents["doc-pending"].google_maps_url is None
    assert repository.documents["doc-pending"].google_maps_search_url is not None
