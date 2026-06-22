# Design: Per-signal cadence & freshness captions

**Date:** 2026-06-21
**Status:** Approved (pending spec review)

## Background

The BTC headline verdict has read a flat "BUY" for ~10 consecutive days. Diagnosis
(see conversation) found this is **by design**, not a pipeline fault: each signal is
quantized to `{0, 50, 100}`, so sub-threshold movement is discarded, and several
inputs are slow by nature. In particular:

- **Monthly RSI** is computed on a month-end resample and forward-filled to daily.
  Its raw value is present every day but only *changes* once a month. The dashboard
  currently presents it like any fresh daily reading — dishonest about its cadence.
- **MVRV / Puell** publish 1–2 days late; `compute_signals._last_valid` carries the
  last valid value forward, so the displayed number is silently older than today.

The user does **not** want to change the scoring math. They want each signal card to
*honestly state* how often it updates and what date its current reading is from, so
they can see at a glance what is live versus legitimately slow.

## Goal

Add a per-signal **freshness caption** to each dashboard signal card:

- **Natural cadence** — `Daily` or `Monthly`, and for slow signals when it next changes.
- **Effective as-of date** — the date the current reading is actually from.

**Non-goal:** any change to the composite score, spectrum position, weights, or verdict.
This is purely additive transparency.

## The "as of" rule (core decision)

`as_of` for a signal = **the date its non-NaN raw value last changed** (the last day the
value differed from the previous non-NaN value). A single rule that resolves all three
real-world cases honestly:

| Case | Series shape | `as_of` resolves to |
|------|-------------|---------------------|
| Monthly RSI | ffilled daily, constant within a month | the month-end the value came from (e.g. May 31) |
| MVRV / Puell lag | trailing NaN (carry-forward) | the last real datapoint (e.g. Jun 18) |
| Normal daily signal | changes every day | today |
| Entirely NaN (warm-up) | all NaN | `None` |

**Why not "date of last non-NaN value":** that rule breaks Monthly RSI. Its series is
forward-filled and therefore *never* NaN, so "last non-NaN" would read today's date for a
value that is really from last month-end — exactly the dishonesty this feature removes.
The as-of must be *last-change*, not *last-present*.

## Data flow (5 touch points, all additive)

```
SignalSpec.cadence ("daily"/"monthly")  ─┐
data/{id}_signal_history.csv ─ as_of ────┼─▶ compute_signals.py  ─▶ current_signals.json: +as_of
                                          ├─▶ score.py           ─▶ {id}_score.json: +cadence +as_of
                                          └─▶ build_dashboard.py ─▶ +next_refresh, format ─▶ blob.signals[].freshness
                                                                     └─▶ template: muted caption line
```

## Components

### 1. Cadence metadata — `assets/base.py`, `assets/bitcoin.py`, `assets/eth.py`
- Add `cadence: str = "daily"` field to the `SignalSpec` dataclass. The default means only
  exceptions need an override.
- Set `cadence="monthly"` on the `monthly_rsi` `SignalSpec` in **both** `bitcoin.py` and
  `eth.py`. Every other signal is honestly daily and needs no change.

### 2. The as-of computation — `scripts/compute_signals.py`
- New pure helper:
  ```python
  def last_change_date(dates: pd.Series, raw: pd.Series) -> Optional[date]
  ```
  Drops NaN from `raw` (keeping aligned dates), then returns the date of the last position
  where the value differs from the previous kept value. If the kept series has a single
  distinct value, return the date of its first occurrence. If empty, return `None`.
- In `_process_asset`, compute `as_of` per spec from the signal-history `date` column and
  the `{key}_raw` column, and add `"as_of": <iso string or null>` to
  `current["signals"][key]`.
- Scores and sell-scores are computed exactly as today. No math change.

### 3. Pass-through — `scripts/score.py`
- For each signal written to `{id}_score.json`, add:
  - `"cadence"` — from the matching `SignalSpec.cadence`.
  - `"as_of"`  — passed through from `current_signals.json`.
- `compute_score` / `compute_spectrum_pos` are untouched.

### 4. Format + next-refresh — `scripts/build_dashboard.py`
- New pure helper computes `next_refresh` for **monthly** signals only: the month-end on or
  after the dashboard's data date. Daily signals have no next-refresh date.
- Assemble one display string per signal into the asset blob (`signals[].freshness`):

  | Cadence / state | Caption |
  |-----------------|---------|
  | Daily, current | `Daily · as of Jun 20` |
  | Daily, lagging | `Daily · as of Jun 18` |
  | Monthly | `Monthly · as of May 31 · next Jun 30` |
  | No data (`as_of` null) | `Daily` (cadence only) |

  Dates render as `Mon D` (e.g. `Jun 20`), consistent with `format_reading` living in this
  module. Year is implied (current). Date formatting stays in the presentation layer.

### 5. Card caption — `templates/dashboard.html.j2`
- In `metricCardHTML`, insert one muted line directly under the name+reading header row,
  before the `mt-auto` bar block:
  ```html
  <div class="text-[10px] text-outline mt-1">Monthly · as of May 31 · next Jun 30</div>
  ```
- Uniform muted grey on every card. No tint, icon, or alarm styling — a lagging signal is
  conveyed solely by showing an older date.
- The existing no-data branch (`No data`) may also show the cadence-only caption.

## Testing

- `tests/test_compute_signals.py` — `last_change_date`:
  - daily-moving series → last date
  - monthly ffill series (constant within month, changes at month-end) → the month-end
  - trailing-NaN series → last non-NaN change date
  - all-NaN series → `None`
- Build helper test — `next_refresh`:
  - data date mid-month → that month-end
  - data date on a month-end → that day
  - freshness string format per cadence (daily / daily-lagging / monthly / no-data)
- **Regression guard:** assert `composite_score` and `spectrum_pos` in `{id}_score.json`
  are byte-identical before/after this change for the existing fixtures. The math must not move.

## Out of scope (YAGNI — each considered and ruled out by the user's choices)

- No weight / composite / spectrum changes.
- No amber tint or "behind" alarm styling.
- No "unchanged for N days" counter (the date framing replaces it).
- No staleness *fault* detection (distinguishing a dead source from a legitimately slow one).
- No new or higher-frequency data sources.
- No dynamic down-weighting of slow signals.
- VEQT is docs-only and not in the asset registry yet — no action.
