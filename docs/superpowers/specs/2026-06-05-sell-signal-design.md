# Kairos — Sell Signal & Spectrum UI Design

**Date:** 2026-06-05  
**Status:** Approved  
**Visual reference:** `docs/superpowers/kairos-spectrum-mockup-reference.png`

---

## Goal

Add a calibrated sell/take-profit signal to the Kairos dashboard, symmetric with the existing buy signal. Replace the one-directional zone strip with a bidirectional spectrum gauge that answers two questions at a glance: "Should I buy?" and "Should I sell?"

---

## Data Model Changes

### `SignalSpec` (assets/base.py)

Add one field:

```python
sell_thresh: float  # raw value above which the signal says "sell" (score = 100)
```

Sell scoring is binary: `sell_score = 100 if raw > sell_thresh else 0`.  
The existing `invest_thresh` / `avoid_thresh` are untouched.

### `AssetConfig` (assets/base.py)

Add two fields:

```python
good_exit: Callable[[pd.DataFrame], pd.Series]   # bool Series — symmetric with good_entry
sell_weight_overrides: Optional[dict[str, float]] = None
```

---

## good_exit() Definitions

### Bitcoin

- Price is within the **top 40%** of the current cycle range (causal: using expanding cycle high, same logic as `_get_cycle_ranges`)
- 18-month forward price falls by **≥ 50%** from that point

```python
CYCLE_TOP_PCT = 0.60   # price >= cycle_low + 0.60*(cycle_high - cycle_low)
HOLDING_DAYS  = 548    # same as good_entry
MIN_DRAWDOWN  = 0.50   # forward drawdown >= 50%
```

### Ethereum

- Price within **top 25%** of the expanding price range (causal: `cycle_high = df["price"].expanding().max()`, `cycle_low = df["price"].expanding().min()`) — avoids the permanently high bar of a fixed all-time high in stagnating markets
- 18-month forward price falls by **≥ 50%**

```python
CYCLE_TOP_PCT = 0.75   # price >= expanding_low + 0.75*(expanding_high - expanding_low)
HOLDING_DAYS  = 548
MIN_DRAWDOWN  = 0.50
```

Both use the same 18-month window and 50% threshold as `good_entry` for symmetry.

---

## Sell Signal Thresholds

### Bitcoin

| Signal | sell_thresh | Rationale |
|---|---|---|
| MVRV Z-Score | 3.5 | Historically marks late-cycle overvaluation |
| 200W MA Ratio | 2.5× | Extreme stretch above long-run trend |
| Monthly RSI | 78 | Cycle tops cluster at 78–85, not just > 70 |
| Pi Cycle | 1.0 | Famous crossover: 111DMA crosses above 2×350DMA |
| Puell Multiple | 3.0 | Miner revenue euphoria |
| Fear & Greed | 78 | Extreme greed zone (zeroed if backtest precision < 30%) |

### Ethereum

| Signal | sell_thresh | Rationale |
|---|---|---|
| MVRV Z-Score | 3.0 | ETH peaks at lower Z-scores than BTC |
| 200W MA Ratio | 2.0× | ETH's MA stretch is typically less extreme |
| Monthly RSI | 78 | Same as BTC |
| ETH/BTC Ratio Z-score | 1.5 | ETH historically expensive vs BTC at cycle tops |
| Mayer Multiple | 2.4 | Classic overbought level on 200DMA |
| Fear & Greed | 78 | Same as BTC (zeroed if precision < 30%) |

---

## Backend Pipeline

### scripts/backtest.py

Add `_backtest_sell_asset(cfg)`:
- Uses `cfg.good_exit(price_df)` as the target boolean series
- Same precision/recall/F1 computation as the buy side
- Zeros out Fear & Greed sell weight if its precision < 0.30
- Writes `data/{asset}_sell_weights.json`

### scripts/compute_signals.py

For each signal, compute alongside existing buy score:
```python
sell_score = 100 if raw > spec.sell_thresh else 0
```
Both buy and sell scores written to:
- `data/{asset}_current_signals.json` (adds `sell_score` per signal)
- `data/{asset}_signal_history.csv` (adds `{key}_sell` columns)

### scripts/score.py

Reads `{asset}_sell_weights.json`, computes:
```python
sell_composite = weighted_average(sell_scores, sell_weights)
```

Spectrum position formula:
```python
# sell_composite only pulls pointer left when meaningfully active (>= 25);
# below that threshold it is treated as 0 so neutral markets stay centered.
effective_sell = sell_composite if sell_composite >= 25 else 0
spectrum_pos = clamp(50 + (buy_composite - effective_sell) / 2, 0, 100)
```

Adds to `{asset}_score.json`:
- `sell_composite` (float)
- `sell_verdict` (str) — thresholds:
  - < 25 → "LOW"
  - 25–50 → "ELEVATED"
  - 50–75 → "HIGH"
  - ≥ 75 → "STRONG SELL"
- `spectrum_pos` (float, 0–100)

### scripts/build_dashboard.py

Reads `spectrum_pos` and `sell_composite` from score JSON.  
Passes both to the Jinja2 template alongside existing asset data.  
`notify.json` gains `spectrum_pos` and `sell_composite` fields per asset.

---

## Spectrum Position Verdicts

| spectrum_pos | Verdict | Color |
|---|---|---|
| 0–25 | TAKE PROFIT | #ff5252 |
| 25–50 | SELL | #ff9800 |
| 50–72 | HOLD | #ffd740 |
| 72–80 | BUY | #00c853 |
| 80–100 | STRONG BUY | #00e676 |

---

## UI — Dashboard Template (templates/dashboard.html.j2)

**Score card replaces** the existing zone strip section only. All other sections unchanged.

### Spectrum gauge

- Five zones with widths proportional to score ranges:
  - TAKE PROFIT: flex 25 (score 0–25, left)
  - SELL: flex 25 (score 25–50)
  - HOLD: flex 22 (score 50–72, center)
  - BUY: flex 8 (score 72–80)
  - STRONG BUY: flex 20 (score 80–100, right)
- White cursor line at `spectrum_pos %` with floating score bubble above it
- Tick labels at zone boundaries: `0 · 25 · 50 · 72 · 80 · 100`, color-coded red→grey→green
- HOLD zone visually centered; buy/sell zones symmetric on each side (implementation note: adjust flex values if needed to achieve visual symmetry)

### Score boxes (below gauge)

Two boxes side by side:
- **Left (red tint):** Sell signal score + sell verdict
- **Right (green tint):** Buy signal score + buy verdict + distance text

### Chip row

Each asset chip keeps its existing mini-sparkline. No change needed here — spectrum_pos feeds the chip verdict label.

### distance_text logic

```python
if spectrum_pos >= 72:
    distance_text = f"{spectrum_pos - 72:.1f} pts into Buy zone"
elif spectrum_pos >= 50:
    distance_text = f"{72 - spectrum_pos:.1f} pts from Buy zone"
elif spectrum_pos >= 25:
    distance_text = f"{spectrum_pos - 25:.1f} pts into Sell zone"
else:
    distance_text = "Take profit zone"
```

---

## Push Notifications (scripts/send_push.py)

Verdict sourced from `spectrum_pos` (not buy score alone).

Format: `"{name} {spectrum_pos:.1f} {arrow} {delta:+.1f} — {verdict}{flag}"`

Flags:
- `" ⚠️"` appended when verdict is TAKE PROFIT or SELL
- `" ✓"` appended when verdict is STRONG BUY

Examples:
- `"Bitcoin 69.7 ↑ +3.2 — BUY"`
- `"Ethereum 22.4 ↓ −4.1 — TAKE PROFIT ⚠️"`
- `"Bitcoin 83.1 ↑ +5.0 — STRONG BUY ✓"`

---

## Files Changed

| File | Change |
|---|---|
| `assets/base.py` | Add `sell_thresh` to SignalSpec; `good_exit` + `sell_weight_overrides` to AssetConfig |
| `assets/bitcoin.py` | Add `sell_thresh` per signal, add `good_exit()` |
| `assets/eth.py` | Add `sell_thresh` per signal, add `good_exit()` |
| `scripts/backtest.py` | Add `_backtest_sell_asset()`, write sell weights |
| `scripts/compute_signals.py` | Compute + store sell scores per signal |
| `scripts/score.py` | Compute sell composite + spectrum_pos |
| `scripts/build_dashboard.py` | Pass sell data to template |
| `templates/dashboard.html.j2` | Replace zone strip with spectrum gauge |
| `scripts/send_push.py` | Update push format to use spectrum_pos verdict |

---

## Out of Scope

- New data sources (all sell signals reuse existing fetched data)
- Per-signal sell bars in the signal table (sell_thresh is used for composite only; the existing buy bars are unchanged)
- Backtest visualisation for sell signals
- Historical sell signal chart overlay
