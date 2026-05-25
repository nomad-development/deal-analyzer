# deal-analyzer

Wholesaling underwriter for real-estate investors. Point it at an MLS export and a
subject property; it runs the standard comp-selection process, estimates ARV,
computes the Maximum Allowable Offer, and returns a **GO / NO-GO** with the comps
and reasoning shown — not a black box.

```
============================================================
  DEAL ANALYSIS — 123 Maple St, Dallas TX
============================================================
  ARV (After Repair Value):   $     264,300
  Repair estimate:            $      35,000
  MAO (Max Allowable Offer):  $     150,000
  Price/sqft range:           $146 - $148
  Comps used:                 6
------------------------------------------------------------
  DECISION:  NO-GO
------------------------------------------------------------
  Comps:
    • 129 Maple St, Dallas TX        $   146/sqft  0.04mi
    • 118 Maple St, Dallas TX        $   148/sqft  0.07mi
    • 140 Oak Ave, Dallas TX         $   146/sqft  0.10mi  [2.5ba vs subject 2.0ba]
    ...
------------------------------------------------------------
  Investor summary:
    123 Maple St — 3bd/2.0ba, 1,800 sqft. ARV $264,300 from 6 comps
    ($146-$148/sqft, tight spread). MAO $150,000 at 70% rule.
    Decision: NO-GO — asking $265,000 exceeds MAO.
============================================================
```

## Why it's built this way

The underwriting math is **deterministic and tested** — distance, recency, sqft
variance, type matching, and outlier removal are pure functions you can audit and
trust. The *judgment* calls that genuinely need a language model — condition
adjustments between a renovated comp and an as-is subject, and the investor-facing
summary — sit behind a swappable `CompAnalyst` interface.

That seam matters: the tool runs **free and offline** with a deterministic stub
analyst today, and upgrades to Claude-written analysis by changing one line —
no pipeline changes, no rewrite. You don't pay per run while iterating, and the
numbers never depend on a model being available or in a good mood.

```
ingest.py   →  comps.py        →  llm.py            →  pipeline.py
(CSV parse)    (8-step filter,    (judgment +          (orchestrates,
               ARV, MAO — all     prose summary,        returns analysis)
               deterministic)     behind interface)
```

## The comping process

Mirrors the standard wholesaler workflow:

1. **Distance** — comps within 0.5 miles (Haversine; skipped if coords absent)
2. **Recency** — sold within 90 days preferred; stale sales dropped
3. **Sqft variance** — within ±15% of the subject
4. **Type match** — single-family compared to single-family, etc.
5. **Outlier removal** — drops comps outside 1.5×IQR on price/sqft
6. **Price/sqft** — computed per comp, bed/bath deltas flagged
7. **ARV** — median adjusted price/sqft × subject sqft (median resists skew)
8. **MAO** — `(ARV × 0.70) − repairs`

Decision: **GO** if asking price ≤ MAO, else **NO-GO**.

Every threshold (`MAX_DISTANCE_MILES`, `SQFT_VARIANCE`, `MAO_ARV_FACTOR`, …) is a
named constant in `comps.py` — tune them to a market without touching logic.

## Usage

```bash
pip install -e .

deal-analyzer analyze \
  --mls data/sample_comps.csv \
  --subject-address "123 Maple" \
  --repairs 35000
```

The MLS parser is tolerant of real-world exports: it maps common header
spellings (`Sold Price` / `Close Price` / `Sale Price`…), strips `$` and commas,
and skips rows with no address or size rather than crashing.

### Enabling the Claude analyst

The model layer is wired but inert by default. To turn it on:

```bash
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=sk-...
```

Then uncomment `ClaudeAnalyst` in `llm.py` and return it from `default_analyst()`.
Defaults to `claude-haiku-4-5` for cents-per-run cost.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite covers each filter independently (a far property, a stale sale, a
mismatched type, an out-of-range size all get excluded), the MAO formula, the
decision logic, and an end-to-end run.

---

Built by [Nomad](https://github.com/nomad-development) · MIT licensed
