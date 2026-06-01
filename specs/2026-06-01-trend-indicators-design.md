# Trend Indicators — Design Spec
**Date:** 2026-06-01

## Goal

Add a Day / Week / Month trend layer to the Kairos dashboard so the user can understand at a glance whether the composite score and individual signals are improving, declining, or flat over time — without having to mentally compare today's number against the historical chart.

---

## What Changes

### 1. Global trend toggle

A Day / Week / Month pill-button toggle sits between the page header and the score card. It controls all trend-related elements simultaneously — the composite delta, the sparkline, and the signal direction arrows.

- Default: **Day** (selected on page load)
- All three datasets are pre-computed at build time and embedded in the HTML; the toggle is pure client-side JavaScript with no network requests.
- The toggle persists in `localStorage` so returning users see their last-used window.

### 2. Composite score card additions

Two new elements are added inside the existing score card, between the verdict and the zone strip:

**Delta line**
```
↑ +2.1 pts vs yesterday
```
- Arrow direction: ↑ if delta > +0.5, ↓ if delta < −0.5, → otherwise (flat)
- Color: green (`#00c853`) for up, red (`#ff5252`) for down, grey (`#888`) for flat
- Label changes with toggle: "vs yesterday" / "vs last week" / "vs last month"

**Sparkline**
- 7 vertical bars sitting below the zone strip, centered in the score card
- Bar heights are proportional to the composite score for each period
- Bars are dark (`#2a2a2a`) except the rightmost (current) bar, which is colored by zone (red/yellow/orange/green)
- Opacity increases left-to-right so recent bars are visually dominant
- On hover/tap: tooltip showing the period label (e.g. "May 26") and the score + zone verdict, e.g. `52.4 — CLOSE`, with the score colored by zone
- Window follows the toggle:
  - Day → last 7 daily composite scores, tooltip labels are calendar dates
  - Week → last 7 weekly composite scores (end-of-week), tooltip labels are week-of dates
  - Month → last 7 monthly composite scores (end-of-month), tooltip labels are month names

### 3. Signal direction arrows (new table column)

A narrow 4th column is added to the signal table, between "Reading" and the bar column. It contains a single direction arrow for each signal.

- Arrow characters: ↑ → ↓ (up / flat / down)
- Arrow color: green for up, yellow for flat, red for down — matching the existing palette
- Flat threshold: score change of 0 (signal scores are integers; any change is meaningful)
- Direction is based on the signal's 0–100 score (not the raw value), compared against the score N periods ago
- Column header: a subtle `▲▼` glyph in muted grey — minimal, doesn't compete with the bar header

### 4. Data pre-computation (`scripts/build_dashboard.py`)

At build time, the dashboard builder computes all trend data and embeds it as a single JSON object in the HTML (`trend_data_json`):

```json
{
  "day":   { "delta": 2.1, "spark": [{"score": 48.2, "label": "May 25"}, ...], "arrows": {"mvrv": 1, "ma": 1, ...} },
  "week":  { "delta": -1.3, "spark": [...], "arrows": {...} },
  "month": { "delta": 8.4,  "spark": [...], "arrows": {...} }
}
```

Arrow values: `1` = up, `0` = flat, `-1` = down.

**Lookback logic:**
- Day: compare today's scores against the row from 1 calendar day ago
- Week: compare against 7 calendar days ago
- Month: compare against 30 calendar days ago
- Sparkline scores for Day/Week/Month: last 7 daily / weekly (resample "W-last") / monthly (resample "ME") composite scores
- If a lookback row is missing (e.g. data gap), fall back to the nearest available prior row; if none exists, arrow is flat and delta is 0

**Composite score for historical rows** is recomputed using `compute_historical_scores()` (already exists in `build_dashboard.py`) — no new pipeline step needed.

---

## What Does Not Change

- `scripts/fetch_data.py`, `scripts/compute_signals.py`, `scripts/score.py` — untouched
- `data/signal_history.csv`, `data/current_score.json` — untouched
- The existing historical chart (BTC price + composite score) — untouched
- The existing zone strip, signal range bars, status badges, methodology section — untouched
- CI/CD pipeline — untouched; all new data is derived from files already present

---

## Files Summary

| File | Change |
|---|---|
| `scripts/build_dashboard.py` | Compute trend data (delta, sparkline, arrows) for all 3 windows; pass `trend_data_json` to template |
| `templates/dashboard.html.j2` | Add toggle, delta line, sparkline (with tooltips), arrow column; add toggle JS |

---

## Verification

1. Run `python scripts/build_dashboard.py` — confirm `docs/index.html` contains `trend_data_json`
2. Open `docs/index.html` locally — toggle Day / Week / Month; verify delta label, sparkline bars, and signal arrows all update
3. Hover each sparkline bar — verify tooltip shows date + score + zone verdict
4. Push; wait for GitHub Pages deploy; verify on mobile (tap to trigger tooltip)
5. Run `python -m pytest -q` — all 30 tests pass (no pipeline changes, no new test surface)

---

## Risks / Known Gotchas

- **Static site constraint**: all three windows' data must be embedded at build time. The toggle is purely JS — no fetch calls. This is already the project pattern (the historical chart data is embedded the same way).
- **Signal score granularity**: signal scores are integers (0, 25, 50, 75, 100 in most cases). Any non-zero delta is meaningful; the flat threshold is exactly 0.
- **Data lag**: MVRV and Puell lag 1–2 days (already handled by `_last_valid()` in `compute_signals.py`). The lookback for "1 day ago" will naturally use the same last-valid row for those signals, so the day delta may show flat for lagged signals even when a week or month shows movement — this is correct and expected behavior.
- **Mobile tooltips**: CSS `:hover` tooltips work on touch via tap-to-reveal / tap-elsewhere-to-dismiss, which is standard browser behavior. No JS needed for this.
