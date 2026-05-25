"""LLM layer for judgment calls the deterministic engine can't make.

Two responsibilities:
  1. Condition/quality adjustments the raw numbers miss (a comp that sold
     renovated vs the subject as-is).
  2. The investor-facing prose summary.

Both sit behind `CompAnalyst` so the pipeline runs with a free, offline stub
today and swaps to a real Anthropic-backed implementation by changing one line
in cli.py — no pipeline changes. This is the seam that keeps tests fast and
the demo zero-cost until real calls are wanted.
"""
from __future__ import annotations

from typing import Protocol

from .models import Comp, DealAnalysis, Property


class CompAnalyst(Protocol):
    """The judgment interface. Implemented by the stub now, Claude later."""

    def summarize(self, analysis: DealAnalysis) -> str:
        """Return a short investor summary for the buyers list."""
        ...


class StubAnalyst:
    """Deterministic, offline stand-in for the Claude analyst.

    Produces a real, usable summary from the computed numbers — good enough to
    demo the full pipeline without an API key or network. Swap for
    ClaudeAnalyst to get model-written prose and condition adjustments.
    """

    def summarize(self, analysis: DealAnalysis) -> str:
        s, a = analysis.subject, analysis
        spread = a.price_per_sqft_high - a.price_per_sqft_low
        confidence = "tight" if spread < 30 else "wide" if spread > 75 else "moderate"
        lines = [
            f"{s.address} — {s.beds}bd/{s.baths}ba, {int(s.sqft):,} sqft "
            f"({s.property_type.value.replace('_', ' ')}).",
            f"ARV ${a.arv:,.0f} from {len(a.comps)} comps "
            f"(${a.price_per_sqft_low:.0f}-${a.price_per_sqft_high:.0f}/sqft, "
            f"{confidence} spread).",
            f"Repairs est. ${a.repair_estimate:,.0f}. "
            f"MAO ${a.mao:,.0f} at {int(70)}% rule.",
            f"Decision: {a.decision}"
            + (
                f" — asking ${s.list_price:,.0f} "
                + ("clears" if a.decision == "GO" else "exceeds")
                + " MAO."
                if s.list_price
                else " — no asking price on file."
            ),
        ]
        return " ".join(lines)


# --- Real implementation (wired but inert until an API key is provided) -------
#
# class ClaudeAnalyst:
#     """Anthropic-backed analyst. Uncomment + `pip install anthropic`, set
#     ANTHROPIC_API_KEY, and pass model='claude-haiku-4-5' for cheap runs."""
#
#     def __init__(self, model: str = "claude-haiku-4-5") -> None:
#         from anthropic import Anthropic
#         self._client = Anthropic()
#         self._model = model
#
#     def summarize(self, analysis: DealAnalysis) -> str:
#         comps_block = "\n".join(
#             f"- {c.property.address}: ${c.adjusted_price_per_sqft:.0f}/sqft, "
#             f"{c.distance_miles:.2f}mi {'; '.join(c.adjustment_notes)}"
#             for c in analysis.comps
#         )
#         prompt = (
#             "You are a real-estate underwriter. Write a 3-4 sentence investor "
#             "summary for a wholesaler's buyers list. Be concrete, no hype.\n\n"
#             f"Subject: {analysis.subject.address}\n"
#             f"ARV ${analysis.arv:,.0f}, repairs ${analysis.repair_estimate:,.0f}, "
#             f"MAO ${analysis.mao:,.0f}, decision {analysis.decision}.\n"
#             f"Comps used:\n{comps_block}"
#         )
#         resp = self._client.messages.create(
#             model=self._model,
#             max_tokens=400,
#             messages=[{"role": "user", "content": prompt}],
#         )
#         return resp.content[0].text.strip()


def default_analyst() -> CompAnalyst:
    """Return the analyst used by default. Stub today; flip to ClaudeAnalyst
    once an API key is configured."""
    return StubAnalyst()
