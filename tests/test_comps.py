"""Tests for the deterministic comping engine and end-to-end pipeline."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from deal_analyzer import comps as ce
from deal_analyzer.ingest import load_properties
from deal_analyzer.models import Property, PropertyType
from deal_analyzer.pipeline import analyze

DATA = Path(__file__).parent.parent / "data" / "sample_comps.csv"
TODAY = date(2026, 5, 1)  # fixed clock so recency filtering is deterministic


def _subject(props):
    return next(p for p in props if p.address.startswith("123 Maple"))


def test_ingest_skips_unusable_and_maps_aliases():
    props = load_properties(DATA)
    # 11 rows in CSV, all have address+sqft -> all parsed
    assert len(props) == 11
    subj = _subject(props)
    assert subj.sqft == 1800
    assert subj.beds == 3
    assert subj.list_price == 265000


def test_distance_filter_excludes_far_property():
    props = load_properties(DATA)
    subj = _subject(props)
    selected = ce.select_comps(subj, [p for p in props if p is not subj], today=TODAY)
    addrs = {c.property.address for c in selected}
    assert not any("Plano" in a for a in addrs)  # ~16mi away


def test_recency_filter_excludes_stale_sale():
    props = load_properties(DATA)
    subj = _subject(props)
    selected = ce.select_comps(subj, [p for p in props if p is not subj], today=TODAY)
    assert not any("Stale" in c.property.address for c in selected)  # sold 2025-06


def test_type_filter_excludes_condo():
    props = load_properties(DATA)
    subj = _subject(props)  # single family
    selected = ce.select_comps(subj, [p for p in props if p is not subj], today=TODAY)
    assert not any("Condo" in c.property.address for c in selected)


def test_sqft_variance_filter():
    props = load_properties(DATA)
    subj = _subject(props)  # 1800 sqft -> window [1530, 2070]
    selected = ce.select_comps(subj, [p for p in props if p is not subj], today=TODAY)
    for c in selected:
        assert abs(c.property.sqft - 1800) / 1800 <= ce.SQFT_VARIANCE


def test_mao_formula():
    # MAO = ARV * 0.70 - repairs, rounded to nearest $100
    assert ce.compute_mao(300000, 40000) == 170000
    assert ce.compute_mao(265000, 35000) == 150500


def test_decision_go_when_asking_under_mao():
    assert ce.decide(mao=170000, asking_price=160000) == "GO"
    assert ce.decide(mao=170000, asking_price=180000) == "NO-GO"
    assert ce.decide(mao=170000, asking_price=None) == "NO-GO"


def test_end_to_end_produces_complete_analysis():
    props = load_properties(DATA)
    subj = _subject(props)
    result = analyze(subj, [p for p in props if p is not subj], repair_estimate=35000, today=TODAY)
    assert result.arv > 0
    assert result.mao == ce.compute_mao(result.arv, 35000)
    assert result.decision in ("GO", "NO-GO")
    assert result.investor_summary  # stub analyst produced prose
    assert len(result.comps) >= 4


def test_no_comps_raises():
    subj = Property(
        address="Isolated", latitude=0.0, longitude=0.0, sqft=1800, beds=3,
        baths=2, sold_price=None, list_price=200000, days_on_market=1,
        property_type=PropertyType.SINGLE_FAMILY, sale_date=None,
    )
    with pytest.raises(ValueError, match="No comps"):
        analyze(subj, [], repair_estimate=10000, today=TODAY)
