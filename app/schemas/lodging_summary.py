from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SummaryAvailability = Literal["available", "sold_out", "unknown"]


class LodgingDecisionSummaryTrip(BaseModel):
    trip_id: str
    title: str
    status: str
    display_token: str


class LodgingDecisionSummaryStats(BaseModel):
    total_lodgings: int = Field(ge=0)
    available_count: int = Field(ge=0)
    sold_out_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)


class LodgingDecisionSummaryLodging(BaseModel):
    document_id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    property_name: str | None = None
    city: str | None = None
    formatted_address: str | None = None
    price_amount: float | None = None
    price_currency: str | None = None
    availability: SummaryAvailability
    is_sold_out: bool | None = None
    amenities: list[str] = Field(default_factory=list, max_length=20)
    maps_url: str | None = None
    target_url: str = Field(min_length=1)
    notion_page_url: str | None = None
    captured_at: datetime | None = None
    updated_at: datetime | None = None


class LodgingDecisionSummaryRequest(BaseModel):
    trip: LodgingDecisionSummaryTrip
    summary: LodgingDecisionSummaryStats
    lodgings: list[LodgingDecisionSummaryLodging] = Field(default_factory=list)


class LodgingDecisionCandidate(BaseModel):
    document_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)


class LodgingDecisionSummaryResponse(BaseModel):
    top_candidates: list[LodgingDecisionCandidate] = Field(
        min_length=1,
        max_length=3,
    )
    pros: list[str] = Field(default_factory=list, max_length=5)
    cons: list[str] = Field(default_factory=list, max_length=5)
    missing_information: list[str] = Field(default_factory=list, max_length=5)
    discussion_points: list[str] = Field(default_factory=list, max_length=5)


LODGING_DECISION_SUMMARY_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "top_candidates": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "display_name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["document_id", "display_name", "reason"],
            },
        },
        "pros": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "cons": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "missing_information": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "discussion_points": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
    },
    "required": [
        "top_candidates",
        "pros",
        "cons",
        "missing_information",
        "discussion_points",
    ],
}
