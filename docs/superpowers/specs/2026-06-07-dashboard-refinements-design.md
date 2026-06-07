# Dashboard Refinements Design

**Date:** 2026-06-07
**Builds on:** the two-view redesign in `templates/dashboard.html.j2` (branch `feat/new-design-redesign`, PR #1).
**Status:** Approved (brainstorming). Next step: implementation plan.

## Goal

Seven UX refinements to the redesigned Kairos dashboard, all driven by user feedback. **Every change is template-only** (`templates/dashboard.html.j2`): all required data already exists in the per-asset `ASSETS` blob, so there are no Python, build-script, data, or test changes. `docs/index.html` is regenerated from the template via `python scripts/build_dashboard.py`.

## Data already available (no changes needed)

Per-asset blob (`ASSETS[i]`):
- `price` (int), `price_unit` ("$"), `display_name`, `short_label`, `spectrum_pos` (0–100 float), `spectrum_verdict`, `score_color`.
- `trend.{day,week,month}.spark` — array of up to 7 `{score, label, verdict}` (oldest→newest).
- `signals[]` — each `{key, display_name, reading, bar}` where `bar` has: `has_data`, `avoid_pct`, `wait_pct`, `invest_pct` (zone widths summing ~100), `thresh_avoid_pct`, `thresh_invest_pct` (divider x-positions), `thresh_avoid_lbl`, `thresh_invest_lbl` (formatted gating values, e.g. "1.5", "-0.5"), `cursor_pct` (current reading position), `status_class` (`st-invest|st-wait|st-avoid`).

Existing JS helpers reused: `zoneColor(score)` (→ emerald/green/grey/amber/red by 80/60/40/20 thresholds).

## The seven changes

### 1. Price onto each card (welcome page)
- Remove the per-asset price from the top app bar. The app bar keeps only the KAIROS wordmark (left) and the "Updated <timestamp>" line (right).
- On each card, render `price_unit + price.toLocaleString()` as a secondary line directly under the coin name (`short_label`), ticker-style, in the emerald data font.

### 2. Score-history tooltip (welcome cards + details histogram)
- Each mini-bar in a score-history chart gets a tooltip shown on hover (desktop) and tap (mobile).
- Tooltip content: `"<label> — <score>"` (e.g. "Jun 5 — 66.2"), where `label` and `score` come from the spark entry. The tooltip text/accent is colored with `zoneColor(score)`. **No price.**
- Tap behavior: tapping a bar toggles its tooltip open (mirroring the prior dashboard's `.tip-open` pattern) so it works without a hover state on touch devices.

### 3. Remove "LIVE" (details page)
- Delete the green status dot and the "LIVE" text from the details context header. Keep the subtitle (`<NAME> DETAILS`).

### 4. Score-history block on details page
- Add a score-history histogram **under the verdict/description, above the metric-cards grid**.
- It has its **own** Day/Week/Month toggle, independent of the welcome page's selection (separate state; may persist under a distinct key, e.g. `kairos-detail-trend-window`).
- Reuses the same bar rendering + tooltip from change #2, driven by the open asset's `trend.{window}.spark`.

### 5. Signal gauges — Layout B (details metric cards)
Each signal card keeps the redesigned thin rounded bar with the white needle, but:
- **Real zone widths:** the bar is three segments using `bar.avoid_pct` / `bar.wait_pct` / `bar.invest_pct` (left→right), tinted red / neutral / emerald. Thin divider ticks at `bar.thresh_avoid_pct` and `bar.thresh_invest_pct`.
- **White needle** at `bar.cursor_pct` (current reading).
- **Inline label row above the bar** (Layout B): `AVOID` (left), the gating value `bar.thresh_avoid_lbl` at `bar.thresh_avoid_pct`, `WAIT` (center), the gating value `bar.thresh_invest_lbl` at `bar.thresh_invest_pct`, `INVEST` (right). Zone words colored dim red/grey/emerald; gate values in light grey.
- **Reading** (top-right of the card) colored by state: `st-invest`→emerald `#00ff88`, `st-wait`→amber `#fdb878`, `st-avoid`→red `#ffb4ab` (unchanged from current).
- No-data signals render the existing "No data" fallback.

### 6. White score needle on the welcome-card range
- The card's 5-zone composite range **keeps its current coloring exactly**: each zone in its base color, the active zone (per `spectrum_pos`) fully lit + glow, the others dimmed (~0.30 opacity).
- Overlay a bright-white needle (2–3px, white glow, `transform: translateX(-50%)`) at `left: spectrum_pos%` marking the current score. This is an addition; the zone-highlight treatment is unchanged.

### 7. "TP" → "STRONG SELL"
- Welcome-card range zone labels become: `STRONG SELL · SELL · HOLD · BUY · STRONG BUY` (the active zone's label stays bold/colored).
- A display mapping renders the verdict word `"TAKE PROFIT"` → `"STRONG SELL"` wherever the verdict appears in the UI (welcome-card verdict line, details hero verdict). Underlying scoring data, the `spectrum_verdict` values, `get_score_color`, and `verdict_description` keys remain `"TAKE PROFIT"` — only the displayed string changes.

## Out of scope / unchanged
- Scoring/signal computation, `scripts/build_dashboard.py`, data files, Python tests.
- The price-vs-composite Chart.js chart and its 6M/1Y/2Y/All pills.
- Alerts page, PWA/service worker, navigation/hash routing.

## Verification
- `python scripts/build_dashboard.py` builds cleanly (2 assets).
- `python -m pytest -q` still green (unchanged, but confirm no accidental breakage).
- Playwright @ 390×844: welcome page shows price under each coin name, white needle on each range, `STRONG SELL` label, and bar tooltips on hover/tap; details page has no "LIVE", a score-history block with its own Day/Week/Month toggle above the metric cards, and signal gauges in Layout B with AVOID/WAIT/INVEST + gating values. Console shows only the expected `/fbtc-timing/` 404s.
