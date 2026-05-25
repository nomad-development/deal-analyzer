"""Core data models for the deal analyzer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PropertyType(str, Enum):
    SINGLE_FAMILY = "single_family"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    MULTI_FAMILY = "multi_family"
    UNKNOWN = "unknown"


@dataclass
class Property:
    """A single property record parsed from an MLS export."""

    address: str
    latitude: float | None
    longitude: float | None
    sqft: float
    beds: int
    baths: float
    sold_price: float | None
    list_price: float | None
    days_on_market: int | None
    property_type: PropertyType
    sale_date: str | None  # ISO date string, None if active/unsold

    @property
    def price_per_sqft(self) -> float | None:
        price = self.sold_price or self.list_price
        if price and self.sqft:
            return round(price / self.sqft, 2)
        return None


@dataclass
class Comp:
    """A comparable property with the adjustments applied to it."""

    property: Property
    distance_miles: float
    adjusted_price_per_sqft: float
    adjustment_notes: list[str] = field(default_factory=list)


@dataclass
class DealAnalysis:
    """The full output of analyzing a subject property."""

    subject: Property
    comps: list[Comp]
    arv: float
    repair_estimate: float
    mao: float
    price_per_sqft_low: float
    price_per_sqft_high: float
    decision: str  # "GO" | "NO-GO"
    investor_summary: str
