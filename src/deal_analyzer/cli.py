"""Command-line entry point for the deal analyzer.

Usage:
    python -m deal_analyzer.cli analyze \\
        --mls data/sample_comps.csv \\
        --subject-address "123 Main St" \\
        --repairs 35000
"""
from __future__ import annotations

import argparse
import sys

from .ingest import load_properties
from .models import DealAnalysis
from .pipeline import analyze


def _find_subject(properties, address):
    needle = address.strip().lower()
    for p in properties:
        if p.address.strip().lower() == needle:
            return p
    # tolerant partial match
    matches = [p for p in properties if needle in p.address.strip().lower()]
    if len(matches) == 1:
        return matches[0]
    return None


def _render(analysis: DealAnalysis) -> str:
    a = analysis
    out = [
        "=" * 60,
        f"  DEAL ANALYSIS — {a.subject.address}",
        "=" * 60,
        f"  ARV (After Repair Value):   ${a.arv:>12,.0f}",
        f"  Repair estimate:            ${a.repair_estimate:>12,.0f}",
        f"  MAO (Max Allowable Offer):  ${a.mao:>12,.0f}",
        f"  Price/sqft range:           ${a.price_per_sqft_low:.0f} - ${a.price_per_sqft_high:.0f}",
        f"  Comps used:                 {len(a.comps)}",
        "-" * 60,
        f"  DECISION:  {a.decision}",
        "-" * 60,
        "  Comps:",
    ]
    for c in a.comps:
        note = f"  [{'; '.join(c.adjustment_notes)}]" if c.adjustment_notes else ""
        out.append(
            f"    • {c.property.address[:38]:38}  "
            f"${c.adjusted_price_per_sqft:>6.0f}/sqft  "
            f"{c.distance_miles:.2f}mi{note}"
        )
    out += ["-" * 60, "  Investor summary:", f"    {a.investor_summary}", "=" * 60]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deal-analyzer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Analyze a subject property against MLS comps")
    a.add_argument("--mls", required=True, help="Path to MLS CSV export")
    a.add_argument("--subject-address", required=True, help="Address of the subject property")
    a.add_argument("--repairs", type=float, default=0.0, help="Repair estimate in dollars")

    args = parser.parse_args(argv)

    if args.command == "analyze":
        properties = load_properties(args.mls)
        subject = _find_subject(properties, args.subject_address)
        if subject is None:
            print(
                f"error: subject '{args.subject_address}' not found (or ambiguous) "
                f"in {args.mls}",
                file=sys.stderr,
            )
            return 1
        candidates = [p for p in properties if p is not subject]
        try:
            result = analyze(subject, candidates, repair_estimate=args.repairs)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(_render(result))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
