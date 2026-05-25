"""The 8-step comping process — deterministic filtering and ARV/MAO math.

This is the core underwriting logic from the spec. It is intentionally
deterministic and testable; the LLM layer (llm.py) sits *on top* of this to
handle judgment calls (condition adjustments, comp ranking, prose summary).
"""
from __future__ import annotations

import math
from datetime import date, datetime
from statistics import median

from .models import Comp, Property

# Tunable parameters — defaults from the job spec's 8-step process.
MAX_DISTANCE_MILES = 0.5
PREFERRED_SALE_WINDOW_DAYS = 90
SQFT_VARIANCE = 0.15
MAO_ARV_FACTOR = 0.70  # MAO = (ARV * 0.70) - repairs


def haversine_miles(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance between two lat/lon points, in miles."""
    r = 3958.8  # Earth radius in miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _days_since_sale(sale_date: str | None, today: date) -> int | None:
    if not sale_date:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            d = datetime.strptime(sale_date, fmt).date()
            return (today - d).days
        except ValueError:
            continue
    return None


def select_comps(
    subject: Property,
    candidates: list[Property],
    today: date | None = None,
    max_distance: float = MAX_DISTANCE_MILES,
    sale_window_days: int = PREFERRED_SALE_WINDOW_DAYS,
    sqft_variance: float = SQFT_VARIANCE,
) -> list[Comp]:
    """Steps 1-6: distance, recency, sqft variance, type match, outlier removal.

    Returns comps sorted by distance. ARV/decision are computed separately so
    the LLM layer can re-rank or annotate before the final number is taken.
    """
    today = today or date.today()
    selected: list[Comp] = []

    for c in candidates:
        if c.address == subject.address:
            continue
        price = c.sold_price or c.list_price
        if not price or not c.price_per_sqft:
            continue  # need a price to comp

        # Step 1: distance filter (skip if either point lacks coordinates)
        distance = 0.0
        if None not in (subject.latitude, subject.longitude, c.latitude, c.longitude):
            distance = haversine_miles(
                subject.latitude, subject.longitude, c.latitude, c.longitude
            )
            if distance > max_distance:
                continue

        # Step 2: recency — prefer sales within the window (soft, sold-only)
        if c.sold_price:
            days = _days_since_sale(c.sale_date, today)
            if days is not None and days > sale_window_days:
                continue

        # Step 3: sqft variance ±15%
        if abs(c.sqft - subject.sqft) / subject.sqft > sqft_variance:
            continue

        # Step 4: property type match
        if (
            subject.property_type != c.property_type
            and c.property_type.value != "unknown"
        ):
            continue

        notes: list[str] = []
        ppsf = c.price_per_sqft
        # Step: bed/bath light adjustment — flag deltas for the LLM/investor.
        if c.beds != subject.beds:
            notes.append(f"{c.beds}bd vs subject {subject.beds}bd")
        if c.baths != subject.baths:
            notes.append(f"{c.baths}ba vs subject {subject.baths}ba")

        selected.append(
            Comp(
                property=c,
                distance_miles=round(distance, 3),
                adjusted_price_per_sqft=ppsf,
                adjustment_notes=notes,
            )
        )

    # Step 5: outlier removal — drop comps >1.5 IQR outside the ppsf quartiles.
    selected = _remove_ppsf_outliers(selected)
    selected.sort(key=lambda x: x.distance_miles)
    return selected


def _remove_ppsf_outliers(comps: list[Comp]) -> list[Comp]:
    if len(comps) < 4:
        return comps  # too few to define outliers meaningfully
    values = sorted(c.adjusted_price_per_sqft for c in comps)
    mid = len(values) // 2
    q1 = median(values[:mid])
    q3 = median(values[-mid:])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [c for c in comps if lo <= c.adjusted_price_per_sqft <= hi]


def compute_arv(subject: Property, comps: list[Comp]) -> tuple[float, float, float]:
    """Step 7: ARV = median adjusted price/sqft * subject sqft.

    Returns (arv, ppsf_low, ppsf_high). Median is used over mean to resist
    skew from any outliers that survived filtering.
    """
    if not comps:
        raise ValueError("No comps survived filtering — cannot estimate ARV")
    ppsfs = sorted(c.adjusted_price_per_sqft for c in comps)
    arv = round(median(ppsfs) * subject.sqft, -2)  # round to nearest $100
    return arv, ppsfs[0], ppsfs[-1]


def compute_mao(arv: float, repair_estimate: float, factor: float = MAO_ARV_FACTOR) -> float:
    """Step 8: MAO = (ARV * factor) - repairs."""
    return round(arv * factor - repair_estimate, -2)


def decide(mao: float, asking_price: float | None) -> str:
    """GO if there's room under MAO; NO-GO if asking exceeds MAO or unknown."""
    if asking_price is None:
        return "NO-GO"  # can't justify a buy without a price to test against
    return "GO" if asking_price <= mao else "NO-GO"
