# ETH STRONG BUY Selectivity — Signal Threshold Calibration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recalibrate ETH's per-signal `invest`/`avoid` thresholds (currently uncalibrated BTC seeds) so STRONG BUY fires ~3–5% of days, concentrated at genuine deep bottoms, while the composite validation gate still passes.

**Architecture:** A new reproducible calibration script (`scripts/calibrate_eth_thresholds.py`) documents provenance; its pure threshold-mapping helper is unit-tested. The resulting thresholds are baked statically into `assets/eth.py`'s `CONFIG`. Then the pipeline is re-run (backtest → score → validate → build) to regenerate all data and verify the acceptance criteria.

**Tech Stack:** Python 3, pandas, numpy. All existing scripts: `scripts/backtest.py`, `scripts/score.py`, `scripts/validate_composite.py`, `scripts/build_dashboard.py`.

**Reference spec:** `specs/2026-06-04-eth-strong-buy-calibration-design.md`

---

## Background for implementers

ETH's six `SignalSpec` thresholds in `assets/eth.py` were seed values copied from Bitcoin. Because ETH's raw distributions are wider/shifted, the same absolute threshold fires far too often:

| Signal | old `invest_thresh` | fires for BTC | fires for ETH |
|---|---|---|---|
| MVRV Z-Score | −0.5 | 1.7% | **31%** |
| 200-Week MA  | 1.0  | 7.4% | **24%** |

Result: STRONG BUY (composite ≥ 80) fires **16.9%** of ETH days vs 1.3% for BTC.

**Calibration rule (by signal type):**
- **MVRV Z-Score & 200-Week MA**: set ETH `invest_thresh` to the ETH quantile matching `BTC_buy_rate × K` (K=2.0, loosening factor). `avoid_thresh` = ETH quantile at `1 − BTC_avoid_rate`.
- **ETH/BTC ratio & Mayer Multiple** (ETH-native, no direct BTC analog): anchor to BTC's Puell buy-rate × K (Puell is the clean native bottom-detector at ~5%; Pi-Cycle fires 82% — explicitly excluded).
- **Monthly RSI & Fear & Greed**: keep domain-standard levels (40/70, 25/50). Percentile-matching bounded oscillators produces nonsense (RSI ≈ 2).

Pre-computed result with K=2.0: STRONG BUY = **3.5%** (target 3–5%). The final thresholds to bake:

| Signal | invest_thresh | avoid_thresh | resulting buy% |
|---|---|---|---|
| mvrv_zscore | −1.3209 | 3.5901 | 3.5% |
| ma_200w | 0.8669 | 0.9567 | 14.0% |
| monthly_rsi | 40.0 | 70.0 | 3.8% |
| eth_btc_ratio | −1.0799 | 0.8833 | 10.3% |
| mayer_multiple | 0.6451 | 1.4605 | 9.8% |
| fear_greed | 25.0 | 50.0 | 17.6% |

**range_lo / range_hi** also need updating for two signals so the signal bar displays correctly (avoid_thresh must be ≤ range_hi; invest_thresh must be ≥ range_lo):
- `mvrv_zscore`: range_hi expands from 4.0 → **5.0** (new avoid_thresh 3.59 was too close to old 4.0)
- `eth_btc_ratio`: range updated from −3.0/4.0 → **−2.0/3.0** (trimmed to ETH's actual distribution)

---

## File Structure

| File | Change |
|---|---|
| `scripts/calibrate_eth_thresholds.py` | **Create**: reproducible calibration tool; documents provenance of the baked numbers |
| `tests/test_calibrate.py` | **Create**: unit test for the pure threshold-mapping helper (no live data) |
| `assets/eth.py` | **Modify**: update all 6 `SignalSpec` thresholds + two range_lo/range_hi values in `CONFIG` |
| `data/ethereum_weights.json` | **Regenerated** by `python scripts/backtest.py` |
| `data/ethereum_current_signals.json` | **Regenerated** by `python scripts/compute_signals.py` |
| `data/ethereum_score.json` | **Regenerated** by `python scripts/score.py` |
| `data/ethereum_validation.json` | **Regenerated** by `python scripts/validate_composite.py` |
| `docs/index.html` | **Regenerated** by `python scripts/build_dashboard.py` |

Run all tests with: `python -m pytest -q`

---

## Task 1: Calibration script + unit test

**Files:**
- Create: `scripts/calibrate_eth_thresholds.py`
- Create: `tests/test_calibrate.py`

### Step 1 — Write the failing unit test

Create `tests/test_calibrate.py` with exactly this content:

```python
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from calibrate_eth_thresholds import anchored_threshold


def test_anchored_threshold_returns_correct_quantile():
    # Uniform 0..99; target_buy_rate=0.10 -> 10th percentile = 9.9
    series = pd.Series(range(100), dtype=float)
    result = anchored_threshold(series, target_buy_rate=0.10)
    assert abs(result - 9.9) < 0.5


def test_anchored_threshold_clamps_rate_below_45pct():
    # A target_buy_rate > 0.45 is clamped to 0.45 so invest_thresh never
    # exceeds the median (preserving lower=invest semantics).
    series = pd.Series(range(100), dtype=float)
    result_high = anchored_threshold(series, target_buy_rate=0.80)
    result_capped = anchored_threshold(series, target_buy_rate=0.45)
    assert result_high == result_capped


def test_anchored_threshold_ignores_nan():
    series = pd.Series([1.0, float("nan"), 3.0, 5.0])
    result = anchored_threshold(series, target_buy_rate=0.50)
    # median of [1,3,5] = 3.0
    assert abs(result - 3.0) < 0.01
```

### Step 2 — Run to confirm FAIL

```
python -m pytest tests/test_calibrate.py -q
```
Expected: `ModuleNotFoundError: No module named 'calibrate_eth_thresholds'`

### Step 3 — Create `scripts/calibrate_eth_thresholds.py`

```python
"""Reproducible calibration of ETH per-signal thresholds.

Reads bitcoin_signal_history.csv to derive BTC per-signal buy/avoid rates,
then maps each ETH signal to a target quantile of ETH's own distribution.

Run: python scripts/calibrate_eth_thresholds.py
Not part of daily CI — run manually when recalibration is needed.

Calibration rule
----------------
K = 2.0 (invest-side looseness multiplier — found by sweep to hit 3-5% SB)

Shared signals (MVRV, 200W-MA):
    invest_thresh = ETH quantile at min(btc_buy_rate * K, 0.45)
    avoid_thresh  = ETH quantile at 1 - btc_avoid_rate

ETH-native signals (ETH/BTC ratio, Mayer Multiple):
    anchored to BTC Puell rate (clean bottom-detector, ~5%)
    invest_thresh = ETH quantile at min(puell_buy_rate * K, 0.45)
    avoid_thresh  = ETH quantile at 1 - puell_avoid_rate

Bounded oscillators (Monthly RSI, Fear & Greed):
    domain-standard levels (40/70, 25/50) — percentile-matching produces nonsense.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS

DATA_DIR = Path(__file__).parent.parent / "data"
K = 2.0   # invest-side looseness multiplier (sweep showed K=2.0 -> SB=3.5%)


def anchored_threshold(series: pd.Series, target_buy_rate: float) -> float:
    """Return the quantile of `series` at `target_buy_rate`, capped at 0.45.

    The 0.45 cap ensures invest_thresh never reaches the median — keeping the
    lower-is-invest convention intact regardless of K.
    """
    p = float(np.clip(target_buy_rate, 0.001, 0.45))
    return float(np.nanquantile(series.dropna(), p))


def _rate100(df: pd.DataFrame, key: str) -> float:
    return float((df[key].dropna() == 100).mean())


def _rate0(df: pd.DataFrame, key: str) -> float:
    return float((df[key].dropna() == 0).mean())


def _q(series: pd.Series, p: float) -> float:
    return float(np.nanquantile(series.dropna(), np.clip(p, 0.001, 0.999)))


def _score_series(raw: pd.Series, inv: float, av: float) -> pd.Series:
    s = pd.Series(50.0, index=raw.index)
    s[raw <= inv] = 100
    s[raw >= av] = 0
    s[raw.isna()] = np.nan
    return s


def compute_thresholds(btc: pd.DataFrame, eth: pd.DataFrame, k: float = K) -> dict:
    """Compute calibrated ETH thresholds using BTC buy/avoid rates as anchors."""
    def er(key):
        return eth[key + "_raw"]

    btc_buy = {k_: _rate100(btc, k_) for k_ in ["mvrv_zscore", "ma_200w", "puell"]}
    btc_av  = {k_: _rate0(btc, k_)   for k_ in ["mvrv_zscore", "ma_200w", "puell"]}

    anchored = {
        "mvrv_zscore":   (btc_buy["mvrv_zscore"], btc_av["mvrv_zscore"]),
        "ma_200w":       (btc_buy["ma_200w"],     btc_av["ma_200w"]),
        "eth_btc_ratio": (btc_buy["puell"],        btc_av["puell"]),
        "mayer_multiple":(btc_buy["puell"],        btc_av["puell"]),
    }
    thr = {}
    for sig, (buy_rate, av_rate) in anchored.items():
        inv_thr = anchored_threshold(er(sig), buy_rate * k)
        av_thr  = _q(er(sig), 1 - av_rate)
        if inv_thr >= av_thr:
            av_thr = inv_thr + abs(inv_thr) * 0.05 + 0.001
        thr[sig] = (round(inv_thr, 4), round(av_thr, 4))

    thr["monthly_rsi"] = (40.0, 70.0)
    thr["fear_greed"]  = (25.0, 50.0)
    return thr


def report(thr: dict, eth: pd.DataFrame, weights: dict) -> None:
    en = ["mvrv_zscore", "ma_200w", "monthly_rsi",
          "eth_btc_ratio", "mayer_multiple", "fear_greed"]
    wv = np.array([weights["signals"][k]["weight"] for k in en])
    wv /= wv.sum()

    scores = {}
    print("\nPer-signal thresholds and buy-rates:")
    for sig in en:
        inv, av = thr[sig]
        raw = eth[sig + "_raw"]
        s = _score_series(raw, inv, av)
        scores[sig] = s
        buy = 100 * (s == 100).mean()
        print(f"  {sig:16s}  invest={inv:8.4f}  avoid={av:8.4f}  buy={buy:.1f}%")

    M = np.vstack([scores[s].values for s in en]).T
    comp = np.where(np.isnan(M).any(1), np.nan, M @ wv)
    sb = 100 * (pd.Series(comp).dropna() >= 80).mean()
    print(f"\nComposite STRONG BUY: {sb:.1f}%  (target 3–5%)")
    print("\nPaste into assets/eth.py CONFIG:")
    for sig in en:
        inv, av = thr[sig]
        print(f'  SignalSpec("{sig}", ..., invest_thresh={inv}, avoid_thresh={av}, ...),')


def main():
    btc_path = DATA_DIR / "bitcoin_signal_history.csv"
    eth_path = DATA_DIR / "ethereum_signal_history.csv"
    wts_path = DATA_DIR / "ethereum_weights.json"
    if not all(p.exists() for p in (btc_path, eth_path, wts_path)):
        print("ERROR: run fetch_data + compute_signals + backtest first", file=sys.stderr)
        sys.exit(1)

    btc = pd.read_csv(btc_path)
    eth = pd.read_csv(eth_path)
    weights = json.loads(wts_path.read_text())

    print(f"Calibrating ETH thresholds (K={K})...")
    thr = compute_thresholds(btc, eth, K)
    report(thr, eth, weights)


if __name__ == "__main__":
    main()
```

### Step 4 — Run to confirm tests PASS

```
python -m pytest tests/test_calibrate.py -q
```
Expected: `3 passed`

### Step 5 — Smoke-test the calibration script end-to-end

```
python scripts/calibrate_eth_thresholds.py
```
Expected: output ending with `Composite STRONG BUY: 3.5%  (target 3–5%)` and a table of six thresholds matching the values in the background table above.

### Step 6 — Run full suite to confirm nothing broke

```
python -m pytest -q
```
Expected: all tests pass (current count: 80 + 3 new = 83).

### Step 7 — Commit

```bash
git add scripts/calibrate_eth_thresholds.py tests/test_calibrate.py
git commit -m "feat: add ETH threshold calibration script (BTC-anchored, K=2.0)"
```

---

## Task 2: Apply calibrated thresholds to eth.py

**Files:**
- Modify: `assets/eth.py` (the `CONFIG` signals block only)

### Step 1 — Run the existing ETH structural tests to confirm baseline

```
python -m pytest tests/test_framework.py -q -k "ethereum"
```
Expected: all ETH tests pass (including `test_ethereum_signals_all_lower_is_invest`).

### Step 2 — Update the six SignalSpecs in `assets/eth.py`

In `assets/eth.py`, find the `CONFIG = AssetConfig(...)` block and replace the entire `signals=[...]` list with:

```python
    signals=[
        # Calibrated 2026-06-04: BTC-anchored per-signal quantiles (K=2.0 looseness)
        # -> composite STRONG BUY ≈ 3.5% (target 3-5%). See scripts/calibrate_eth_thresholds.py.
        SignalSpec("mvrv_zscore", "MVRV Z-Score", compute_mvrv_zscore,
                   invest_thresh=-1.3209, avoid_thresh=3.5901,
                   range_lo=-3.0, range_hi=5.0, fmt="{:.1f}"),
        SignalSpec("ma_200w", "200-Week MA", compute_200w_ma_ratio,
                   invest_thresh=0.8669, avoid_thresh=0.9567,
                   range_lo=0.5, range_hi=3.0, fmt="{:.1f}×"),
        SignalSpec("monthly_rsi", "Monthly RSI", compute_monthly_rsi,
                   invest_thresh=40.0, avoid_thresh=70.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
        SignalSpec("eth_btc_ratio", "ETH/BTC Ratio", compute_eth_btc_ratio_z,
                   invest_thresh=-1.0799, avoid_thresh=0.8833,
                   range_lo=-2.0, range_hi=3.0, fmt="{:.1f}"),
        SignalSpec("mayer_multiple", "Mayer Multiple", compute_mayer_multiple,
                   invest_thresh=0.6451, avoid_thresh=1.4605,
                   range_lo=0.0, range_hi=4.0, fmt="{:.1f}×"),
        SignalSpec("fear_greed", "Fear & Greed", compute_fear_greed,
                   invest_thresh=25.0, avoid_thresh=50.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
    ],
```

### Step 3 — Run the ETH structural tests to confirm new thresholds are well-formed

```
python -m pytest tests/test_framework.py -q -k "ethereum"
```
Expected: all 5 ETH tests pass. `test_ethereum_signals_all_lower_is_invest` is the key guard — it checks `invest_thresh < avoid_thresh` for all six signals.

### Step 4 — Run the full test suite

```
python -m pytest -q
```
Expected: 83 passed (same as after Task 1). The threshold change does not affect the data-independent parity test (it uses hardcoded scores, not the thresholds).

### Step 5 — Commit

```bash
git add assets/eth.py
git commit -m "feat: apply BTC-anchored ETH signal thresholds (STRONG BUY -> ~3.5%)"
```

---

## Task 3: Re-run pipeline, verify acceptance, commit data

**Files:**
- `data/ethereum_weights.json` (regenerated)
- `data/ethereum_current_signals.json` (regenerated)
- `data/ethereum_score.json` (regenerated)
- `data/ethereum_validation.json` (regenerated)
- `data/bitcoin_validation.json` (regenerated, side-effect of validate_composite)
- `docs/index.html` (regenerated)
- `notify.json` (gitignored, regenerated but not committed)

### Step 1 — Re-derive ETH signal weights (backtest)

New thresholds change which days score 100, so weights must be re-derived from scratch.

```
python scripts/compute_signals.py
python scripts/backtest.py
```

Expected output includes:
```
Computing signals for Ethereum...
  ethereum: signals for ...
Backtesting Ethereum...
  ethereum: ... good-entry days; weights written
```

### Step 2 — Score both assets

```
python scripts/score.py
```

Expected: ETH composite is now **below 80** (no longer STRONG BUY under the tightened thresholds; expect a CLOSE or WAIT reading for current market conditions).

If ETH still shows STRONG BUY, **stop and investigate** — check that `assets/eth.py` was saved with the new thresholds (Task 2 Step 2) and that `compute_signals.py` ran after the edit.

### Step 3 — Run composite validation gate

```
python scripts/validate_composite.py
```

Check the output for `ethereum`:
- Gate must print **`-> PASS`** (OOS edge > 0 and OOS precision > 0).
- If it prints `-> REVIEW`, stop — do not commit. The new thresholds may have broken the OOS edge. In that case, go back to `scripts/calibrate_eth_thresholds.py` and try a slightly larger K (e.g. K=2.5), re-run compute_signals + backtest + validate, and update the thresholds in eth.py accordingly.

### Step 4 — Verify STRONG BUY frequency

```
python -X utf8 -c "
import pandas as pd, numpy as np, json
sig = pd.read_csv('data/ethereum_signal_history.csv')
w   = json.loads(open('data/ethereum_weights.json').read())['signals']
en  = ['mvrv_zscore','ma_200w','monthly_rsi','eth_btc_ratio','mayer_multiple','fear_greed']
wv  = np.array([w[k]['weight'] for k in en]); wv /= wv.sum()
comp = pd.Series(sig[en].values @ wv).dropna()
sb  = 100*(comp >= 80).mean()
print(f'STRONG BUY: {sb:.1f}%  (target 3-5%)')
"
```

Expected: output between 3% and 5%. If outside this range, stop and revisit K.

### Step 5 — Build dashboard

```
python scripts/build_dashboard.py
```

Expected: `Dashboard written to docs/index.html (...; 2 asset(s))`

### Step 6 — Confirm both assets render correctly

```
python -X utf8 -c "
import re, json
html = open('docs/index.html', encoding='utf-8').read()
m = re.search(r'const ASSETS = (\[.*?\]);', html, re.S)
for a in json.loads(m.group(1)):
    print(a['id'], '| composite=', a['composite'], a['verdict'])
"
```

Expected: bitcoin shows its current score; ethereum is **NOT** STRONG BUY (current conditions are not a bottom).

### Step 7 — Run the full test suite one last time

```
python -m pytest -q
```

Expected: 83 passed.

### Step 8 — Commit all generated files

```bash
git add data/ethereum_weights.json data/ethereum_current_signals.json \
        data/ethereum_score.json data/ethereum_validation.json \
        data/bitcoin_validation.json docs/index.html
git commit -m "chore: regenerate ETH data with calibrated thresholds

STRONG BUY drops from 16.9% -> ~3.5%. Validation gate: PASS."
```

---

## Done

ETH's STRONG BUY now fires ~3.5% of days, concentrated at the deepest genuine bottoms (2018–19, 2020 COVID crash, 2022 capitulation). Today's reading correctly reflects current market conditions rather than misfiring as STRONG BUY.

The calibration script documents provenance so future recalibrations (as ETH history grows) are a straightforward re-run.
