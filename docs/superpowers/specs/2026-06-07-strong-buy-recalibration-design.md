# STRONG BUY Recalibration — Design

**Date:** 2026-06-07
**Status:** Approved (pending spec review)

## Problem

The dashboard headline shows **STRONG BUY** far more loosely than intended. On 2026-06-07 Bitcoin reads STRONG BUY even though its two deep-value signals (MVRV Z-Score and Puell Multiple) sit in the neutral zone, not INVEST. The user expects STRONG BUY to be a rare, earned flag — roughly the top ~5% (refined below to ~3%) of days, reserved for genuinely strong entry conditions.

### Root cause

There are two different "STRONG BUY" definitions in the system and they disagree:

| Verdict | Rule | Historical frequency (BTC, 5,604 mature days) |
|---|---|---|
| Buy **composite** verdict (`get_verdict`) | composite ≥ 80 | 1.4% of days |
| Spectrum **headline** (`get_spectrum_verdict`) | spectrum ≥ 80 | **8.4% of days** |

The headline shown to users is the *spectrum*, computed as `spectrum = 50 + (buy − effective_sell) / 2`. When the sell side is quiet (`sell = 0`, as today), the spectrum reaches 80 as soon as the **buy composite is only 60** — i.e. a mere "BUY". So a buy composite of 66.2 ("BUY") is stretched into a spectrum of 83.1 ("STRONG BUY"). The gauge relabels BUY as STRONG BUY.

On STRONG BUY days historically, the value signals are usually *not* in INVEST: MVRV 21%, Monthly RSI 0%, Puell 44%. The flag is carried by trend signals (Pi Cycle 98%, 200-Week MA 78%). Today is the norm, not an exception.

### What is NOT broken

The spectrum *ranking* works: forward 18-month returns are monotonic by band (STRONG BUY +237% median / 100% win, BUY +182%, HOLD +33%, SELL −12%). The fix is about making the **label honest and rare**, not about fixing a broken ranking.

## Decision

**Recalibrate the spectrum STRONG BUY cutoff per asset**, chosen empirically to target ~3% of days. No change to signal weights, signal thresholds, `good_entry`/`good_exit`, or the spectrum formula. This is purely a labeling cutoff.

### Why ~3% and not 5%

A threshold sweep across all history showed precision against the `good_entry` ground truth is 1.00 at every cutoff (on assets that mostly rose, almost any buy eventually looks good), so the ground truth cannot pick the number — it is a judgment call about rarity. The user chose ~3% because, unlike the ~5% setting, it makes *today* correctly step down from STRONG BUY to BUY, resolving the exact case that prompted this work.

### Calibrated cutoffs (from the sweep)

| Asset | Cutoff | % of days flagged | Median fwd 18mo | Today steps down to BUY? |
|---|---|---|---|---|
| Bitcoin | **85** (buy ≥ 70) | 2.9% | +302% | Yes (was 83.1) |
| Ethereum | **88** (buy ≥ 76) | 3.3% | +135% | Yes (was 87.7) |

ETH runs hotter than BTC — a single global 85 would give ETH 5.3%, which is why the cutoff is per-asset. Default for any future asset is 85.

## Architecture

The STRONG BUY threshold (`80`) is currently duplicated across four locations. The design centralizes it as a per-asset config value so future recalibration touches one place.

### 1. `assets/base.py` — new config field
Add `strong_buy_cutoff: float = 85.0` to `AssetConfig`. Default 85 so existing/new assets behave as the Bitcoin baseline unless overridden.

### 2. `assets/bitcoin.py` / `assets/eth.py`
- Bitcoin: rely on the default (or set `strong_buy_cutoff=85.0` explicitly for clarity).
- Ethereum: set `strong_buy_cutoff=88.0`.

### 3. `scripts/score.py` — source of truth for the verdict
- `get_spectrum_verdict(spectrum_pos, cutoff)` takes the asset's cutoff and uses `>= cutoff` for the STRONG BUY band (other bands: BUY ≥ 60, HOLD ≥ 40, SELL ≥ 20, else TAKE PROFIT, unchanged — the BUY band simply widens to 60–cutoff).
- `_score_asset` passes `cfg.strong_buy_cutoff`.
- Emit `strong_buy_cutoff` into `{asset}_score.json` so downstream consumers (template, build_dashboard) read it instead of hardcoding.

### 4. `scripts/build_dashboard.py`
- `distance_text` logic (currently `>= 80` and the literal "80" in "pts from Strong Buy") reads the asset's cutoff from the score JSON.
- The per-asset payload embedded into the template carries `strong_buy_cutoff` (default 85 if absent, for backward compatibility with older score files).

### 5. `templates/dashboard.html.j2` — gauge visuals follow the cutoff
The green STRONG BUY zone boundary must match the new label:
- `zoneColor` (line ~231) and `zoneIndex` (line ~235): replace the hardcoded `80` boundary with the asset's `strong_buy_cutoff` from the embedded JSON.
- Detail-chart band annotations (lines ~437–438): the `{min:80,max:100}` / `{min:60,max:80}` boundary becomes the asset's cutoff.

## Explicit non-goals

- The standalone **composite** verdict (`get_verdict`, STRONG BUY at ≥ 80, ~1.4% of days) is unchanged — it is not the headline. The spectrum may still read more bullish than the composite verdict; this is inherent to the spectrum design the user chose to keep.
- No change to signal weights, signal INVEST/AVOID/SELL thresholds, or `good_entry`/`good_exit`.
- No "conviction gate" requiring specific value signals to be in INVEST (considered and set aside in favor of pure recalibration).

## Testing

- `tests/test_sell_signal.py::test_get_spectrum_verdict`: assert band edges with an explicit cutoff — e.g. at cutoff 85, `84 → "BUY"` and `85 → "STRONG BUY"`; at cutoff 88, `87 → "BUY"` and `88 → "STRONG BUY"`. Cover the default-cutoff path too.
- `tests/test_push.py` (line ~123): the STRONG BUY fixture passes an explicit verdict string so it still passes; update its `spectrum_pos` to a value ≥ the new cutoff to keep the fixture self-consistent.
- Add/extend a test asserting `AssetConfig.strong_buy_cutoff` default is 85 and ETH's is 88 (alongside existing registry/config tests).
- Full suite (`pytest`, 80 tests) green.

## Verification

- Run `scripts/compute_signals.py` → `scripts/score.py` → `scripts/build_dashboard.py` for both assets.
- Confirm Bitcoin headline flips STRONG BUY → BUY (spectrum 83.1 < 85) and Ethereum flips STRONG BUY → BUY (spectrum 87.7 < 88).
- Confirm the rendered gauge green zone now begins at 85 (BTC) / 88 (ETH) and the white needle sits in the BUY zone for both today.

## Risks / notes

- This is a labeling cutoff with no look-ahead concerns; the spectrum formula and weights are untouched.
- Older `{asset}_score.json` files written before this change won't contain `strong_buy_cutoff`; consumers default to 85 when the field is absent.
- The daily CI workflow regenerates score + dashboard, so the live site updates on the next run without a backtest.
