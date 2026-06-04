# ETH STRONG BUY selectivity — BTC-anchored signal calibration — Design

**Date:** 2026-06-04
**Status:** Approved (design)

## Problem

ETH's composite verdict lands in **STRONG BUY 16.9% of all days** (670 / 3953),
versus Bitcoin's **1.3%**. A "back up the truck" signal that fires one day in six is
not actionable. The signal is also noisy (many 0–3 day flickers) and currently reads
95.4 / STRONG BUY even though ETH is only *cheap-ish*, not at a genuine bottom.

### Root cause (measured)

ETH reused Bitcoin's **absolute** seed thresholds, but ETH's distributions are wider /
shifted, so the same numbers are far too lenient. The same `invest_thresh` fires at
wildly different rates per asset:

| Signal | seed `invest_thresh` | fires for BTC | fires for ETH |
|---|---|---|---|
| MVRV Z-Score | −0.5 | 1.7% | **31.0%** |
| 200-Week MA | 1.0 | 7.6% | **24.5%** |
| Monthly RSI | 40 | 1.1% | 3.9% |
| Fear & Greed | 25 | 22.9% | 22.9% (shared index) |

MVRV < −0.5 is a rarity for BTC but routine for ETH. Those two high-weight signals
(≈0.48 combined weight) drive most of the over-firing.

## Goal & acceptance criteria

Recalibrate ETH's per-signal `invest`/`avoid` thresholds so that, under the **unchanged**
global ≥80 STRONG BUY band:

- STRONG BUY fires **3–5% of days**, concentrated at genuine deep bottoms.
- OOS verdict bands remain **monotonic** in forward return.
- STRONG BUY **OOS precision ≥ 0.9**.
- The composite validation gate still **PASSES** (OOS edge > 0).

Bitcoin, the verdict bands, the scoring engine, and the dashboard/template are untouched.

## Non-goals

- No change to the verdict-band cutoffs (80/72/50/25) or to making them per-asset
  (deliberately rejected — it would touch `score.py`, `build_dashboard`, the Jinja
  zone-strip, the client `zoneColor` JS, and tests for little gain here).
- No change to Bitcoin's config, the six ETH signals themselves, `weight_overrides`
  (stays `None`), or the scoring engine.
- No new daily-CI step (calibration is a manual/dev tool, like the backtest).

## Calibration rule (per-signal, by type)

For each signal a **target buy-rate** (fraction of days scoring 100) is chosen; the ETH
`invest_thresh` is then the quantile of ETH's own historical raw series at that rate
(lower = invest). `avoid_thresh` is set symmetrically from the avoid-rate anchor, except
where a domain value is kept.

- **MVRV Z-Score & 200-Week MA** — high-weight, badly mismatched. Target buy-rate =
  **BTC's realized buy-rate** for the same signal (≈1.7%, ≈7.4%). Yields ETH
  `invest_thresh` ≈ −1.48 (deep MVRV z) and ≈0.74 (price ~26% below the 200-week MA) —
  both sensible deep-value levels.
- **ETH/BTC ratio & Mayer Multiple** — ETH-native, no clean BTC analog. Target buy-rate =
  **BTC's Puell buy-rate (~5%)**, a clean native bottom-detector. Explicitly **not**
  Pi-Cycle, which scores "buy" 82% of the time (a top-detector) and would poison the
  anchor. Yields Mayer `invest_thresh` ≈ 0.52 (≈48% below the 200-day MA), a true-capitulation level.
- **Monthly RSI & Fear & Greed** — bounded oscillators. **Keep domain-standard levels**
  (RSI 40/70, F&G 25/50). Percentile-matching them produces nonsense (RSI ≈ 2.2). Fear &
  Greed is a shared market-wide index, so ETH keeps the same value BTC uses.
- **Global looseness multiplier `k`** — one scalar applied to all anchored buy-rates.
  BTC-anchoring alone lands ETH at ~2.1% (stricter than target, since it pulls ETH toward
  BTC's own selectivity). `k` (≈1.5–2, tuned) scales the anchored rates up to bring the
  final composite STRONG BUY into 3–5%, preserving BTC-relative per-signal strictness
  while hitting the absolute target.

All resulting thresholds must preserve `invest_thresh < avoid_thresh` (the scorer's
lower-is-invest convention).

## Mechanism / where it lives

- **`scripts/calibrate_eth_thresholds.py`** (new, dev-only, not in CI): reads
  `bitcoin_signal_history.csv` to compute BTC anchor rates, maps each ETH signal to its
  target buy/avoid rate per the rule above (with `k`), computes the ETH-quantile
  thresholds, and prints the proposed thresholds + resulting per-signal buy-rates +
  composite STRONG BUY %. Documents provenance so the baked numbers are reproducible, not
  magic. Mirrors the existing analysis-script pattern (`validate_composite.py`).
- The chosen threshold values are **baked statically into `assets/eth.py`'s `CONFIG`**
  (same pattern as today — thresholds are static, re-derived on demand like weights), with
  a comment citing the calibration method and `k`.
- Then re-run the pipeline: `backtest` (re-derive `ethereum_weights.json`), `score`,
  `validate_composite`, `build_dashboard`.

## Expected effect (illustrative, existing weights)

Refined thresholds and their ETH buy-rates from the design simulation:

| Signal | invest | avoid | ETH buy-rate |
|---|---|---|---|
| MVRV Z-Score | −1.48 | 3.59 | 1.7% |
| 200-Week MA | 0.74 | 0.96 | 7.0% |
| Monthly RSI | 40 (domain) | 70 | 3.8% |
| ETH/BTC ratio | −1.43 | 0.88 | 5.2% |
| Mayer Multiple | 0.52 | 1.46 | 4.9% |
| Fear & Greed | 25 (domain) | 50 | 17.6% |

Composite STRONG BUY ≈ 2.1% before applying `k`; `k` is tuned during implementation to
reach 3–5%. Today's ETH (≈$1,816) moves from STRONG BUY (95.4) to a measured
CLOSE/INVEST — the intended correction (today is cheap, not capitulation).

## Acceptance check

Run `validate_composite` plus a STRONG BUY frequency report. Pass iff: STRONG BUY ∈
[3,5]%, OOS bands monotonic, STRONG BUY OOS precision ≥ 0.9, gate PASS. If outside range,
adjust `k` and re-run. Do not bake thresholds until the check passes.

## Testing

- Existing `tests/test_framework.py` structural checks still hold (ETH still has the six
  signals; every `invest_thresh < avoid_thresh`). Keep these; they guard the new values'
  ordering.
- Add a small unit test for the calibration helper's pure mapping (BTC rate → ETH quantile
  threshold) on a synthetic distribution, so the calibration logic is covered without
  depending on live data.
- Do **not** add a data-dependent test asserting the exact STRONG BUY % (it would break on
  daily refreshes); the frequency check lives in the acceptance step, not the test suite.

## Risks

- **Few ETH cycles** (~2–3 bottoms) → thresholds rest on limited data. Mitigated by
  anchoring to BTC's structure rather than overfitting ETH's handful of bottoms.
- **Static thresholds drift** as ETH matures. Mitigated by the reproducible calibration
  script for periodic re-runs (like the backtest workflow).
- **Visible headline change**: ETH's verdict will drop from STRONG BUY to CLOSE/INVEST
  today. Intended and expected.
