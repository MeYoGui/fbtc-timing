# Chart Window & Score Zone Bands Redesign

## Problem

The historical chart shows all data from 2010, making recent price and score movements unreadable. A first-time viewer cannot distinguish the current signal from noise across 15 years of compressed data. The score line (composite 0–100) also lacks visual context — there are no cues indicating which zone (STRONG BUY / BUY / HOLD / SELL / TAKE PROFIT) the score currently sits in.

## Design Decisions

1. **Time-window pills above the chart.** Four options — `6M`, `1Y`, `2Y`, `All` — placed in a pill row directly above the chart canvas. Default is `1Y`. Matches the visual language of the existing Day/Week/Month trend toggle.

2. **Client-side slicing, no Python change.** `build_chart_data` already embeds all weekly data in the page JSON. The window toggle slices the tail of the `dates`, `prices`, `scores` arrays in JS before passing to Chart.js. No rebuild, no data file change.

3. **Window persists in localStorage.** Key `kairos-chart-window`. Restored on page load; falls back to `1Y` if absent or invalid. On asset switch, the current window is preserved (same behaviour as trend window).

4. **Score zone bands as phantom datasets.** Five constant-line datasets on the `yScore` axis fill the chart background with spectrum zone colours:
   - 0–20: `#ff525210` (TAKE PROFIT / red)
   - 20–40: `#ff980010` (SELL / orange)
   - 40–60: `#ffffff08` (HOLD / grey)
   - 60–80: `#00c85310` (BUY / green)
   - 80–100: `#00e67610` (STRONG BUY / bright green)

   These datasets have `pointRadius: 0`, no legend entry (`display: false`), and are stacked between pairs of constant y-values using Chart.js `fill: '+1'` / boundary fill. The score line (`#4dd0a7`) is thickened to `borderWidth: 2`. The price line stays at `opacity: 0.6` so the score line reads as the primary signal.

5. **No changes to anything else.** Signal table, chips, spectrum gauge, trend sparkline, breakdown panel, methodology accordion, Python scripts, data files — all untouched.

## Scope

Template-only change to `templates/dashboard.html.j2`.

- New CSS: `.chart-controls` pill row
- New JS state: `chartWindow` variable, `setChartWindow(w)` function
- Modified JS: `renderChart(a)` accepts a data object (sliced or full), `renderAsset(a)` slices before calling `renderChart`
- Modified HTML: `<div class="chart-controls">` inserted above `<canvas id="chart">`

## Window Sizes

| Pill | Weeks of data |
|------|--------------|
| 6M   | 26           |
| 1Y   | 52 (default) |
| 2Y   | 104          |
| All  | full array   |

## Zone Band Implementation Detail

Five phantom datasets are prepended to the Chart.js `datasets` array. Each is a flat horizontal line (all values equal to the zone boundary). Fill is drawn between adjacent datasets using `fill: '+1'` on the lower boundary dataset.

```js
// Example pair: BUY zone (60–80)
{ label: '', data: labels.map(() => 80), yAxisID: 'yScore',
  borderWidth: 0, pointRadius: 0, fill: '+1',
  backgroundColor: '#00c85310', borderColor: 'transparent',
  legend: { display: false } },
{ label: '', data: labels.map(() => 60), yAxisID: 'yScore',
  borderWidth: 0, pointRadius: 0, fill: false,
  borderColor: 'transparent' },
```

Five zones = 10 boundary datasets (each zone needs a top and bottom line; adjacent zones share a boundary line, so in practice 6 unique boundary lines covering 0, 20, 40, 60, 80, 100, with fill drawn between each pair).

The `plugins.legend.labels.filter` function filters out datasets with an empty label string so they don't appear in the legend.

## Out of Scope

- No changes to `build_chart_data` or any Python script
- No changes to data files or scoring logic
- No Chart.js plugin dependencies (zone bands use native fill)
- No interactive zoom or pan (pills are the only navigation)
- No per-signal chart breakdowns
