from __future__ import annotations

import asyncio
from typing import Sequence

from app.map_enrichment.job import (
    retry_all_map_enrichment_documents,
    run_map_enrichment_job,
)
from app.map_enrichment.models import (
    EnrichedLodgingMap,
    MapEnrichmentCandidate,
)


class InMemoryMapEnrichmentRepository:
    def __init__(self, items: Sequence[MapEnrichmentCandidate]) -> None:
        self.items = list(items)
        self.resolved: dict[str, EnrichedLodgingMap] = {}
        self.failed: dict[str, str] = {}

    def find_pending(
        self,
        limit: int | None,
        source_scope=None,
    ) -> Sequence[MapEnrichmentCandidate]:
        if limit is None:
            return self.items
        return self.items[:limit]

    def find_all(
        self,
        limit: int | None = None,
        source_scope=None,
    ) -> Sequence[MapEnrichmentCandidate]:
        if limit is None:
            return self.items
        return self.items[:limit]

    def find_failed(
        self,
        limit: int,
        source_scope=None,
    ) -> Sequence[MapEnrichmentCandidate]:
        return self.items[:limit]

    def mark_resolved(
        self,
        document_id: str,
        enrichment: EnrichedLodgingMap,
    ) -> None:
        self.resolved[document_id] = enrichment

    def mark_failed(self, document_id: str, error: str) -> None:
        self.failed[document_id] = error


class FakeMapEnrichmentService:
    def __init__(
        self,
        results: dict[str, EnrichedLodgingMap | None],
        failing_urls: set[str] | None = None,
    ) -> None:
        self.results = results
        self.failing_urls = failing_urls or set()
        self.calls: list[str] = []

    async def enrich(self, url: str) -> EnrichedLodgingMap | None:
        self.calls.append(url)
        if url in self.failing_urls:
            raise RuntimeError("simulated fetch failure")
        return self.results.get(url)


def test_run_map_enrichment_job_marks_resolved_and_failed_documents() -> None:
    resolved_url = "https://www.booking.com/hotel/jp/resol.html"
    address_only_url = "https://www.agoda.com/zh-tw/foo/hotel/tokyo-jp.html"
    failing_url = "https://www.booking.com/hotel/jp/failing.html"
    repository = InMemoryMapEnrichmentRepository(
        [
            MapEnrichmentCandidate("doc-1", "https://short.example/1", resolved_url),
            MapEnrichmentCandidate("doc-2", address_only_url),
            MapEnrichmentCandidate("doc-3", failing_url),
        ]
    )
    service = FakeMapEnrichmentService(
        results={
            resolved_url: EnrichedLodgingMap(
                property_name="Hotel Resol Ueno",
                latitude=35.712345,
                longitude=139.778901,
                property_type="hotel",
                amenities=("Free WiFi",),
                price_amount=18000,
                price_currency="JPY",
                google_maps_url=(
                    "https://www.google.com/maps/search/?api=1"
                    "&query=35.712345%2C139.778901"
                ),
                map_source="structured_data_geo",
            ),
            address_only_url: None,
        },
        failing_urls={failing_url},
    )

    summary = asyncio.run(
        run_map_enrichment_job(
            repository=repository,
            service=service,
            limit=10,
        )
    )

    assert summary.processed == 3
    assert summary.resolved == 1
    assert summary.partial == 0
    assert summary.details_resolved == 1
    assert summary.pricing_resolved == 1
    assert summary.failed == 2
    assert repository.resolved["doc-1"].property_name == "Hotel Resol Ueno"
    assert "doc-2" in repository.failed
    assert repository.failed["doc-3"] == "simulated fetch failure"
    assert service.calls == [resolved_url, address_only_url, failing_url]


def test_run_map_enrichment_job_marks_partial_when_only_search_metadata_exists() -> None:
    url = "https://www.booking.com/hotel/jp/resol.html"
    repository = InMemoryMapEnrichmentRepository(
        [MapEnrichmentCandidate("doc-1", url)]
    )
    service = FakeMapEnrichmentService(
        results={
            url: EnrichedLodgingMap(
                property_name="Hotel Resol Ueno",
                formatted_address="7-2-9 Ueno, Taito City, Tokyo, JP",
                google_maps_search_url=(
                    "https://www.google.com/maps/search/?api=1"
                    "&query=7-2-9+Ueno%2C+Taito+City%2C+Tokyo%2C+JP"
                ),
                map_source="booking_header_address",
            )
        }
    )

    summary = asyncio.run(
        run_map_enrichment_job(
            repository=repository,
            service=service,
            limit=10,
        )
    )

    assert summary.processed == 1
    assert summary.resolved == 0
    assert summary.partial == 1
    assert summary.details_resolved == 0
    assert summary.pricing_resolved == 0
    assert summary.failed == 0
    assert repository.resolved["doc-1"].google_maps_search_url is not None


def test_run_map_enrichment_job_marks_airbnb_partial_metadata_as_partial() -> None:
    url = "https://www.airbnb.com/rooms/123456789"
    repository = InMemoryMapEnrichmentRepository(
        [MapEnrichmentCandidate("doc-airbnb", url)]
    )
    service = FakeMapEnrichmentService(
        results={
            url: EnrichedLodgingMap(
                resolved_url=url,
                resolved_hostname="airbnb.com",
                property_name="Shinjuku Loft",
                google_maps_search_url=(
                    "https://www.google.com/maps/search/?api=1&query=Shinjuku+Loft"
                ),
                map_source="airbnb_html_title_fallback",
            )
        }
    )

    summary = asyncio.run(
        run_map_enrichment_job(
            repository=repository,
            service=service,
            limit=10,
        )
    )

    assert summary.processed == 1
    assert summary.resolved == 0
    assert summary.partial == 1
    assert summary.failed == 0
    assert repository.resolved["doc-airbnb"].resolved_hostname == "airbnb.com"


def test_retry_all_map_enrichment_documents_processes_all_candidates() -> None:
    failed_url = "https://www.booking.com/hotel/jp/retry-me.html"
    resolved_url = "https://www.booking.com/hotel/jp/already-resolved.html"
    repository = InMemoryMapEnrichmentRepository(
        [
            MapEnrichmentCandidate("doc-failed", failed_url),
            MapEnrichmentCandidate("doc-resolved", resolved_url),
        ]
    )
    service = FakeMapEnrichmentService(
        results={
            failed_url: EnrichedLodgingMap(
                property_name="Retry Hotel",
                latitude=35.1,
                longitude=139.2,
                property_type="hotel",
                price_amount=12000,
                price_currency="JPY",
                google_maps_url=(
                    "https://www.google.com/maps/search/?api=1"
                    "&query=35.1%2C139.2"
                ),
                map_source="structured_data_geo",
            ),
            resolved_url: EnrichedLodgingMap(
                property_name="Still Good Hotel",
                latitude=35.2,
                longitude=139.3,
                property_type="hotel",
                amenities=("Breakfast",),
                price_amount=15000,
                price_currency="JPY",
                google_maps_url=(
                    "https://www.google.com/maps/search/?api=1"
                    "&query=35.2%2C139.3"
                ),
                map_source="structured_data_geo",
            ),
        }
    )

    summary = asyncio.run(
        retry_all_map_enrichment_documents(
            repository=repository,
            service=service,
        )
    )

    assert summary.processed == 2
    assert summary.resolved == 2
    assert summary.partial == 0
    assert summary.details_resolved == 2
    assert summary.pricing_resolved == 2
    assert summary.failed == 0
    assert repository.resolved["doc-failed"].property_name == "Retry Hotel"
    assert repository.resolved["doc-resolved"].property_name == "Still Good Hotel"
