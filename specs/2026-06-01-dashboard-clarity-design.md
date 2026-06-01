# Dashboard Clarity — Design Spec
**Date:** 2026-06-01

## Goal

Make the investment decision instantly legible. A visitor should know in under three seconds whether to act or wait, and how far they are from the threshold that would change that.

---

## What Changes

### 1. Score Card — Zone Strip

**Before:** Large number + text verdict ("ACCUMULATE", "STRONG BUY"). Labels are ambiguous ("Accumulate" could mean buy or wait).

**After:** Large number + new verdict label + a horizontal zone strip showing position on a 0–100 scale.

#### New zone labels and thresholds

| Zone | Score range | Color | Meaning |
|---|---|---|---|
| AVOID | 0–24 | Red `#ff5252` | Stay out |
| WAIT | 25–49 | Yellow `#ffd740` | Not close |
| CLOSE | 50–71 | Amber `#ff9800` | Getting warm, not yet |
| INVEST | 72–79 | Green `#00c853` | Act — enter a position |
| STRONG BUY | 80–100 | Bright green `#00e676` | Maximum conviction |

The 80 threshold for STRONG BUY is data-derived: scores ≥ 80 have historically occurred only at the 2011, 2015, and 2018 cycle bottoms (76 days total out of 5796 scored). The max score ever recorded is 88.3.

#### Zone strip layout

- Horizontal bar, full width of score card, subdivided into 5 proportional colour segments
- Segment widths: AVOID=25, WAIT=25, CLOSE=22, INVEST=8, STRONG BUY=20 (flex units, proportional to score ranges)
- A bright white vertical cursor marks the current score position
- Threshold labels pinned to zone boundaries: `0` (red), `25` (yellow), `50` (amber), `72` (green), `80` (bright green), `100` (grey)
- Below the strip: distance label — `"X.X pts from Invest zone"` when score < 72, `"You are in the Invest Zone"` when 72 ≤ score < 80, `"You are in the Strong Buy zone"` when score ≥ 80

#### Score number colour

Inherits zone colour: red / yellow / amber / green / bright green.

---

### 2. Signal Table — Range Bars

**Before:** Signal name + reading + coloured dot + text status ("Buy Zone", "Neutral", "Avoid").

**After:** Signal name + reading + a range bar showing the signal's actual raw value against its invest/avoid thresholds.

#### Bar design

- Direction: **left = AVOID (red) → right = INVEST (green)** — consistent with the composite zone strip
- For signals where a lower raw value = better (all six signals), the scale is displayed in reverse order (high value on left, low value on right)
- Three coloured zone segments: avoid (red) | wait (yellow) | invest (green), widths proportional to the signal's actual threshold ranges
- Two thin grey vertical threshold lines at the invest and avoid boundaries
- A bright white cursor (with diamond top) extends above and below the bar to indicate current value — no label on the bar itself, value is in the Reading column
- A status badge above the bar: `WAIT · X from invest`, `INVEST · deep in zone`, `AVOID`, etc.
- Edge labels: `"AVOID [max_value]"` on the left, `"[min_value] INVEST"` on the right
- Threshold values labelled at the grey boundary lines

#### Per-signal ranges and thresholds

| Signal | Display range (left→right) | Avoid threshold | Invest threshold |
|---|---|---|---|
| MVRV Z-Score | 4 → −3 | 1.5 | −0.5 |
| 200-Week MA ratio | 3.0× → 0.5× | 1.2× | 1.0× |
| Monthly RSI | 100 → 0 | 70 | 40 |
| Pi Cycle ratio | 1.5 → 0 | 1.0 | 0.9 |
| Puell Multiple | 4 → 0 | 1.5 | 0.5 |
| Fear & Greed | 100 → 0 | 50 | 25 |

Signals with `null` raw values (currently MVRV Z-Score, Puell Multiple) render the bar faded at 20% opacity with "No data" in place of the status badge and no cursor.

#### Column header

The Range column header reads `← Avoid · · · · · · · · · · · · · · Invest →` to orient the reader immediately.

---

## What Does Not Change

- Scoring logic in `score.py` — thresholds, weights, `compute_score()` all stay identical
- `backtest.py` — no changes
- Historical chart — unchanged
- Methodology section — unchanged
- Data pipeline (`fetch_data.py`, `compute_signals.py`) — unchanged except for exposing threshold metadata (see below)

---

## Data Change: Threshold Metadata

`score.py` writes a `"signal_meta"` block into `current_score.json` alongside the existing `"signals"` block. This gives `build_dashboard.py` everything it needs to render the bars without hardcoding ranges in the template.

```json
"signal_meta": {
  "mvrv_zscore":  { "range_lo": -3.0, "range_hi": 4.0,  "invest_thresh": -0.5, "avoid_thresh": 1.5  },
  "ma_200w":      { "range_lo":  0.5, "range_hi": 3.0,  "invest_thresh":  1.0, "avoid_thresh": 1.2  },
  "monthly_rsi":  { "range_lo":  0.0, "range_hi": 100.0,"invest_thresh": 40.0, "avoid_thresh": 70.0 },
  "pi_cycle":     { "range_lo":  0.0, "range_hi": 1.5,  "invest_thresh":  0.9, "avoid_thresh": 1.0  },
  "puell":        { "range_lo":  0.0, "range_hi": 4.0,  "invest_thresh":  0.5, "avoid_thresh": 1.5  },
  "fear_greed":   { "range_lo":  0.0, "range_hi": 100.0,"invest_thresh": 25.0, "avoid_thresh": 50.0 }
}
```

These values are constants sourced from `compute_signals.py` — single source of truth, written once into the JSON at score time.

---

## Files Modified

| File | Change |
|---|---|
| `scripts/score.py` | Add `SIGNAL_META` constant dict; write `signal_meta` into `current_score.json`; update `get_verdict()` to return new zone labels (AVOID / WAIT / CLOSE / INVEST / STRONG BUY) with thresholds 25 / 50 / 72 / 80 |
| `scripts/build_dashboard.py` | Pass `signal_meta` from `current_score.json` to Jinja2 template context; update `score_color` mapping for the five new zones |
| `templates/dashboard.html.j2` | Replace score card verdict with zone strip; replace signal table status column with range bars |
| `tests/test_score.py` | Update verdict boundary tests to cover all five zones (25, 50, 72, 80) |

---

## Score Number Colour Mapping

| Zone | Colour |
|---|---|
| AVOID | `#ff5252` |
| WAIT | `#ffd740` |
| CLOSE | `#ff9800` |
| INVEST | `#00c853` |
| STRONG BUY | `#00e676` |

---

## Distance Label Logic

```
score < 72  → "{72 - score:.1f} pts from Invest zone"
72 ≤ score < 80  → "You are in the Invest Zone"
score ≥ 80  → "You are in the Strong Buy zone"
```
