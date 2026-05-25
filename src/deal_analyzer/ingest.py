"""MLS CSV ingestion — tolerant column mapping for messy real-world exports."""
from __future__ import annotations

import csv
from pathlib import Path

from .models import Property, PropertyType

# MLS exports vary wildly by region/vendor. Map many possible header spellings
# onto our canonical fields. Lookups are case-insensitive and whitespace-trimmed.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "address": ("address", "full address", "property address", "site address"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lng", "lon", "long"),
    "sqft": ("sqft", "square feet", "living area", "gla", "sq ft", "total sqft"),
    "beds": ("beds", "bedrooms", "br", "bed"),
    "baths": ("baths", "bathrooms", "ba", "bath", "total baths"),
    "sold_price": ("sold price", "sale price", "close price", "sold", "closed price"),
    "list_price": ("list price", "asking price", "list", "original list price"),
    "days_on_market": ("dom", "days on market", "cdom"),
    "property_type": ("property type", "type", "prop type", "style"),
    "sale_date": ("sale date", "sold date", "close date", "closing date"),
}

_TYPE_KEYWORDS: dict[PropertyType, tuple[str, ...]] = {
    PropertyType.SINGLE_FAMILY: ("single", "sfr", "detached"),
    PropertyType.CONDO: ("condo", "condominium"),
    PropertyType.TOWNHOUSE: ("town", "townhome", "attached"),
    PropertyType.MULTI_FAMILY: ("multi", "duplex", "triplex", "fourplex"),
}


def _build_header_map(headers: list[str]) -> dict[str, str]:
    """Map a canonical field -> the actual header present in this CSV."""
    normalized = {h.strip().lower(): h for h in headers}
    resolved: dict[str, str] = {}
    for field_name, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                resolved[field_name] = normalized[alias]
                break
    return resolved


def _parse_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned or cleaned.lower() in ("n/a", "na", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    val = _parse_float(raw)
    return int(val) if val is not None else None


def _classify_type(raw: str | None) -> PropertyType:
    if not raw:
        return PropertyType.UNKNOWN
    low = raw.lower()
    for ptype, keywords in _TYPE_KEYWORDS.items():
        if any(k in low for k in keywords):
            return ptype
    return PropertyType.UNKNOWN


def load_properties(csv_path: str | Path) -> list[Property]:
    """Parse an MLS CSV export into Property records, skipping unusable rows."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"MLS export not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        hmap = _build_header_map(list(reader.fieldnames))

        missing = {"address", "sqft"} - hmap.keys()
        if missing:
            raise ValueError(
                f"CSV missing required column(s): {', '.join(sorted(missing))}. "
                f"Found headers: {', '.join(reader.fieldnames)}"
            )

        properties: list[Property] = []
        for row in reader:
            sqft = _parse_float(row.get(hmap.get("sqft", "")))
            address = (row.get(hmap.get("address", "")) or "").strip()
            if not address or not sqft:
                continue  # unusable row — no address or no size to comp on
            properties.append(
                Property(
                    address=address,
                    latitude=_parse_float(row.get(hmap.get("latitude", ""))),
                    longitude=_parse_float(row.get(hmap.get("longitude", ""))),
                    sqft=sqft,
                    beds=_parse_int(row.get(hmap.get("beds", ""))) or 0,
                    baths=_parse_float(row.get(hmap.get("baths", ""))) or 0.0,
                    sold_price=_parse_float(row.get(hmap.get("sold_price", ""))),
                    list_price=_parse_float(row.get(hmap.get("list_price", ""))),
                    days_on_market=_parse_int(row.get(hmap.get("days_on_market", ""))),
                    property_type=_classify_type(row.get(hmap.get("property_type", ""))),
                    sale_date=(row.get(hmap.get("sale_date", "")) or "").strip() or None,
                )
            )
        return properties
