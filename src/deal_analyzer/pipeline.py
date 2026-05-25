"""Orchestrates the full analysis: ingest -> comp -> ARV/MAO -> summary."""
from __future__ import annotations

from datetime import date

from . import comps as comp_engine
from .llm import CompAnalyst, default_analyst
from .models import DealAnalysis, Property


def analyze(
    subject: Property,
    candidates: list[Property],
    repair_estimate: float,
    analyst: CompAnalyst | None = None,
    today: date | None = None,
) -> DealAnalysis:
    """Run the 8-step process end to end and return a complete DealAnalysis."""
    analyst = analyst or default_analyst()

    selected = comp_engine.select_comps(subject, candidates, today=today)
    arv, ppsf_low, ppsf_high = comp_engine.compute_arv(subject, selected)
    mao = comp_engine.compute_mao(arv, repair_estimate)
    decision = comp_engine.decide(mao, subject.list_price)

    analysis = DealAnalysis(
        subject=subject,
        comps=selected,
        arv=arv,
        repair_estimate=repair_estimate,
        mao=mao,
        price_per_sqft_low=ppsf_low,
        price_per_sqft_high=ppsf_high,
        decision=decision,
        investor_summary="",
    )
    analysis.investor_summary = analyst.summarize(analysis)
    return analysis
