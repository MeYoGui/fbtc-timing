# Add Ethereum (ETH) as a second asset — Design

**Date:** 2026-06-03
**Status:** Approved (design)

## Summary

Add Ethereum as a second config-driven asset to the Kairos timing dashboard, using
the **exact Bitcoin methodology**: compute per-signal raw values → score each signal
(100 buy / 50 neutral / 0 avoid) → label historical "good entries" → derive signal
weights by precision against that label → composite score + verdict → render through
the existing dashboard / PWA / push pipeline.

ETH appears as a second chip alongside Bitcoin. **Bitcoin stays the default asset**
(first in the registry). Because the pipeline is already registry-driven, this is a
config-only change plus two new shared signal functions — **no edits to
`fetch_data`/`compute_signals`/`score`/`backtest`/`build_dashboard`/`send_push`.**

## Goals

- Empirically-selected ETH signals (native or shared) chosen for predictive accuracy,
  the same way BTC weights are derived.
- Keyless data sources only, so the daily GitHub Actions run stays free and
  secret-free (CoinMetrics community API + alternative.me).
- Zero pipeline-script changes; everything loops `ASSETS`.

## Non-goals

- ETH-native fundamentals that need API keys or have too-short history
  (staking ratio via beacon chain, EIP-1559 fee burn / net issuance). Deferred.
- Any change to Bitcoin's signals, weights, or default-asset status.
- Workflow/cron changes.

## New / changed files

| File | Change |
|---|---|
| `assets/eth.py` | **New.** ETH `AssetConfig`: `fetch()`, 6 `SignalSpec`s, `good_entry()`, `weight_overrides`. |
| `assets/signals.py` | **Add** `compute_eth_btc_ratio_z` and `compute_mayer_multiple`. Existing functions reused unchanged. |
| `assets/registry.py` | Append `eth.CONFIG` to `ASSETS` (after `bitcoin.CONFIG`). |
| `scripts/validate_composite.py` | **New.** Backtests the **composite** score (not just per-signal) over full history; loops `ASSETS` so BTC gets it too. In-sample report + walk-forward out-of-sample check. |
| `tests/test_framework.py` | Add ETH config/registry assertions + a **data-independent** ETH scoring-parity fixture. |

## Data fetch (`eth.fetch()`, keyless)

- **CoinMetrics community API** (`assets=eth,btc`, metrics `PriceUSD,CapMrktCurUSD,CapMVRVCur`,
  `frequency=1d`, paged): ETH price / market cap / MVRV, **plus BTC `PriceUSD`** for the
  ETH/BTC ratio signal. History from **2015-08-08** (verified live). One call covers both
  assets; pivot so each row has `price` (ETH) and `btc_price`.
- **alternative.me** Fear & Greed index (crypto-wide; same source BTC uses).
- **No** blockchain.info miner-revenue fetch (Puell is dropped for ETH).
- Output columns: `date, price, market_cap, mvrv, btc_price, fear_greed`.

## Signal pool

All signals are oriented **"lower raw value = more invest"**, which is what
`compute_signals.signal_score` requires (`value <= invest_thresh → 100`,
`value >= avoid_thresh → 0`, else 50).

| Signal (key) | Source | Reused? | Start invest / avoid | Direction note |
|---|---|---|---|---|
| `mvrv_zscore` | CoinMetrics MVRV | reuse | −0.5 / 1.5 | low = undervalued |
| `ma_200w` | price | reuse | 1.0 / 1.2 | low = near/below 200w MA |
| `monthly_rsi` | price | reuse | 40 / 70 | low = oversold |
| `eth_btc_ratio` | ETH/BTC z-score | **new** | −0.5 / 1.0 | low = ETH cheap vs BTC |
| `mayer_multiple` | price ÷ 200-day MA | **new** | 0.8 / 2.4 | low = cheap vs trend |
| `fear_greed` | alternative.me | reuse | 25 / 50 | low = fearful |

**Dropped vs BTC:** `puell` (no miner revenue after the Sept 2022 Merge) and
`pi_cycle` (halving-specific, meaningless without halvings).

### New signal functions (in `assets/signals.py`)

- `compute_mayer_multiple(df)` → `df["price"] / df["price"].rolling(200).mean()`.
- `compute_eth_btc_ratio_z(df)` → `ratio = df["price"] / df["btc_price"]`, returned as a
  full-history z-score `(ratio - ratio.mean()) / ratio.std()` (mirrors `compute_mvrv_zscore`).

### Threshold calibration

The starting thresholds above are seeds. Implementation includes a **calibration pass**
that sets each signal's `invest_thresh` / `avoid_thresh` from ETH's own historical
distribution (e.g. invest ≈ lower quantile, avoid ≈ upper quantile of the raw series),
then the backtest weights by precision so weak signals self-attenuate toward zero weight.
Final thresholds are recorded in `assets/eth.py`.

## Good-entry target (backtest ground truth)

ETH has no halving cycle, so the BTC cycle-bottom definition cannot be reused.
`good_entry(df)` returns a boolean Series true when **both** hold, both tunable:

- **Drawdown from running ATH:** `price[t] <= (1 - DRAWDOWN) * expanding_max(price)[t]`.
  Start **`DRAWDOWN = 0.55`** (≥55% below the all-time high). `expanding_max` is causal —
  no look-ahead.
- **Strong forward return:** `(price[t + HOLDING_DAYS] - price[t]) / price[t] >= MIN_RETURN`.
  Start **`MIN_RETURN = 0.50`**, **`HOLDING_DAYS = 548`** (18 months, same as BTC).

The last `HOLDING_DAYS` rows have no forward window and are labeled `False` (same as BTC).

## Composite-score validation (`scripts/validate_composite.py`)

The existing pipeline derives **per-signal** weights by precision but never checks the
**composite** score. This deliverable validates that the combined score is actually
predictive of good ETH entries over full history, and acts as a **ship gate** for ETH.
The script loops `ASSETS` (so it also reports on Bitcoin) and writes
`data/{id}_validation.json` plus a printed summary. Two complementary analyses:

### 1. In-sample report (final weights, all history)

- Reconstruct the daily composite series from `{id}_signal_history.csv` × final weights.
- For each verdict band (STRONG BUY ≥80 / INVEST ≥72 / CLOSE ≥50 / WAIT ≥25 / AVOID <25):
  day count, **mean & median 18-month forward return**, and % of days with positive
  forward return. A healthy model shows forward return rising monotonically with the band.
- **Precision / recall / F1 of "composite ≥ 72 (INVEST)"** against the `good_entry` label.
- **Vs buy-and-hold:** mean forward return of INVEST-signaled days compared to the mean
  forward return of all days (the edge from timing).

### 2. Walk-forward out-of-sample

- Expanding window: starting after a warm-up (~4 years, so the 200-week MA exists), step
  forward (e.g. monthly). At each step *t*, derive weights using **only** data up to *t*
  (good entries are knowable only up to *t* − 548 days), then score the next out-of-sample
  window with those weights.
- Aggregate **OOS** INVEST precision and OOS forward-return-by-band, and report the
  **in-sample minus OOS gap** as an overfitting indicator.

### Ship gate

If the **out-of-sample** composite does not beat buy-and-hold on INVEST-day forward return
and show better-than-chance INVEST precision, we iterate on thresholds / signal pool before
ETH goes live — rather than shipping a hindsight-fit model. This script is an analysis tool
(manual run / optional workflow dispatch), **not** part of the daily CI job.

## UI / display

`AssetConfig` fields: `id="ethereum"`, `display_name="Ethereum"`,
`short_label="Ξ Ethereum"`, `accent_color="#627eea"`, `price_unit="$"`.
The template renders all assets client-side from embedded JSON (one chip per asset),
so **no template edits**. `build_dashboard` sets `default_asset = assets[0]["id"]`,
which remains `bitcoin`.

## Data files produced

Standard per-asset set, written by the existing scripts:
`data/ethereum_history.csv`, `data/ethereum_signal_history.csv`,
`data/ethereum_current_signals.json`, `data/ethereum_score.json`,
`data/ethereum_weights.json`.

## Ops

- `daily.yml` and `backtest.yml` already loop `ASSETS`; no workflow edits. ETH weights
  are produced by the manual "Re-derive Signal Weights" dispatch (like BTC), then the
  daily run consumes `ethereum_weights.json`.
- Daily push digest (`notify.json` → `send_push.py`) already emits one line per asset;
  ETH joins automatically once it has a `score.json`.

## Testing

- Reuse the data-independent parity approach: add an inline ETH fixture (synthetic
  signals + weights) that pins a known composite/verdict, so daily data refreshes never
  break the suite.
- Add assertions that `eth.CONFIG` is well-formed (6 signals, lower=invest ordering,
  `id="ethereum"`) and present in `ASSETS` after `bitcoin.CONFIG`.

## Risks

- **Fewer cycles → thinner statistics.** ETH has roughly 2–3 historical bottoms
  (2018, 2020 COVID, 2022) versus BTC's halving structure, so precision-derived weights
  rest on less data. Mitigation: the drawdown+forward-return target yields more labeled
  "good" days than a strict cycle-bottom rule, and thresholds are calibrated to ETH's
  distribution rather than hand-tuned to BTC's.
- **Fear & Greed is crypto-wide (BTC-dominated).** Acceptable as a sentiment proxy; the
  backtest will down-weight it if it is not predictive for ETH.
- **ETH/BTC orientation.** Low ETH/BTC = ETH cheap relative to BTC is treated as
  invest-favorable; if the backtest shows it is not predictive, its weight drops out.
