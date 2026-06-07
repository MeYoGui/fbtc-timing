# Chart Window & Score Zone Bands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6M/1Y/2Y/All time-window pills above the chart (default 1Y, persisted in localStorage) and score zone bands behind the score line so the composite score is immediately readable.

**Architecture:** Template-only change to `templates/dashboard.html.j2`. Three passes: (1) CSS + HTML for the pill row, (2) JS state + slicing + zone bands + renderChart/renderAsset wiring, (3) final build, tests, push. Build with `python scripts/build_dashboard.py` after each task. Verification is visual — open `docs/index.html` in a browser.

**Tech Stack:** HTML, CSS, vanilla JS, Chart.js 4.4.0 (already loaded via CDN), Jinja2 template.

---

### Task 1: Add chart controls CSS and HTML

**Files:**
- Modify: `templates/dashboard.html.j2`

Adds the pill row above the chart canvas. After this task the pills appear in the DOM but clicking them does nothing yet (JS comes in Task 2).

- [ ] **Step 1: Add `.chart-controls` and `.chart-pill` CSS**

Inside the `<style>` block, find the line:

```css
    .chart-wrap { margin-bottom: 2rem; }
```

Replace it with:

```css
    .chart-wrap { margin-bottom: 2rem; }
    .chart-controls { display: flex; gap: 6px; justify-content: flex-end; margin-bottom: 0.5rem; }
    .chart-pill { background: #1e1e1e; color: #555; border: none; border-radius: 20px; padding: 4px 14px; font-size: 12px; font-weight: 700; cursor: pointer; transition: background .15s, color .15s; }
    .chart-pill.active { background: #fff; color: #000; }
```

- [ ] **Step 2: Add pill row HTML above the chart canvas**

In the HTML body, find:

```html
  <div class="chart-wrap"><canvas id="chart" height="120"></canvas></div>
```

Replace it with:

```html
  <div class="chart-wrap">
    <div class="chart-controls">
      <button id="cw-6m"  class="chart-pill" onclick="setChartWindow('6m')">6M</button>
      <button id="cw-1y"  class="chart-pill" onclick="setChartWindow('1y')">1Y</button>
      <button id="cw-2y"  class="chart-pill" onclick="setChartWindow('2y')">2Y</button>
      <button id="cw-all" class="chart-pill" onclick="setChartWindow('all')">All</button>
    </div>
    <canvas id="chart" height="120"></canvas>
  </div>
```

Note: no `active` class is hardcoded on any pill — Task 2's JS sets the correct active state on every render.

- [ ] **Step 3: Build**

```
python scripts/build_dashboard.py
```

Expected: `Dashboard written to docs/index.html (... bytes; 2 asset(s))`

Open `docs/index.html`. Verify:
- Four small grey pills (6M, 1Y, 2Y, All) appear right-aligned above the chart
- Chart still renders (all history, unchanged for now)
- No console errors

- [ ] **Step 4: Commit**

```
git add templates/dashboard.html.j2
git commit -m "feat: add chart window pill row HTML and CSS"
```

---

### Task 2: Wire chart window JS and zone bands

**Files:**
- Modify: `templates/dashboard.html.j2`

This task adds the `chartWindow` state, the `sliceChartData` helper, the `setChartWindow` function, rewrites `renderChart` to draw zone bands, and updates `renderAsset` to pass sliced data and sync the active pill.

- [ ] **Step 1: Add chartWindow state and helper functions**

Inside the first `<script>` block, find:

```js
    let chart = null;
```

Replace it with:

```js
    let chart = null;
    var chartWindow = (function () {
      try { var w = localStorage.getItem('kairos-chart-window'); if (['6m','1y','2y','all'].includes(w)) return w; } catch (e) {}
      return '1y';
    })();

    function sliceChartData(c, w) {
      var n = { '6m': 26, '1y': 52, '2y': 104 }[w];
      if (!n) return c;
      var start = Math.max(0, c.dates.length - n);
      return { dates: c.dates.slice(start), prices: c.prices.slice(start), scores: c.scores.slice(start) };
    }

    function setChartWindow(w) {
      chartWindow = w;
      try { localStorage.setItem('kairos-chart-window', w); } catch (e) {}
      ['6m','1y','2y','all'].forEach(function (k) {
        document.getElementById('cw-' + k).classList.toggle('active', k === w);
      });
      renderChart(sliceChartData(BY_ID[currentId].chart, chartWindow));
    }
    window.setChartWindow = setChartWindow;
```

- [ ] **Step 2: Replace renderChart to use sliced data and draw zone bands**

Find the entire `renderChart` function:

```js
    function renderChart(a) {
      const d = a.chart;
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById('chart'), {
        type: 'line',
        data: { labels: d.dates, datasets: [
          { label: a.display_name + ' Price (USD)', data: d.prices, yAxisID: 'yPrice', borderColor: a.accent_color, borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
          { label: 'Composite Score', data: d.scores, yAxisID: 'yScore', borderColor: '#4dd0a7', borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
        ]},
        options: {
          responsive: true, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { labels: { color: '#888', boxWidth: 12, font: { size: 11 } } } },
          scales: {
            x: { ticks: { color: '#555', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yPrice: { type: 'logarithmic', position: 'left', ticks: { color: '#555', font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yScore: { position: 'right', min: 0, max: 100, ticks: { color: '#555', font: { size: 10 } }, grid: { drawOnChartArea: false } },
          },
        },
      });
    }
```

Replace it entirely with:

```js
    function renderChart(d) {
      var a = BY_ID[currentId];
      var zoneBandsPlugin = {
        id: 'zoneBands',
        beforeDraw: function (ch) {
          var ctx = ch.ctx;
          var yAxis = ch.scales.yScore;
          var xAxis = ch.scales.x;
          var zones = [
            { min: 80, max: 100, color: '#00e67610' },
            { min: 60, max: 80,  color: '#00c85310' },
            { min: 40, max: 60,  color: '#ffffff08' },
            { min: 20, max: 40,  color: '#ff980010' },
            { min: 0,  max: 20,  color: '#ff525210' },
          ];
          zones.forEach(function (z) {
            ctx.fillStyle = z.color;
            ctx.fillRect(
              xAxis.left,
              yAxis.getPixelForValue(z.max),
              xAxis.right - xAxis.left,
              yAxis.getPixelForValue(z.min) - yAxis.getPixelForValue(z.max)
            );
          });
        },
      };
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById('chart'), {
        type: 'line',
        data: { labels: d.dates, datasets: [
          { label: a.display_name + ' Price (USD)', data: d.prices, yAxisID: 'yPrice', borderColor: a.accent_color, borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
          { label: 'Composite Score', data: d.scores, yAxisID: 'yScore', borderColor: '#4dd0a7', borderWidth: 2, pointRadius: 0, tension: 0.1 },
        ]},
        options: {
          responsive: true, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { labels: { color: '#888', boxWidth: 12, font: { size: 11 } } } },
          scales: {
            x: { ticks: { color: '#555', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yPrice: { type: 'logarithmic', position: 'left', ticks: { color: '#555', font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yScore: { position: 'right', min: 0, max: 100, ticks: { color: '#555', font: { size: 10 } }, grid: { drawOnChartArea: false } },
          },
        },
        plugins: [zoneBandsPlugin],
      });
    }
```

Key differences from the original:
- Signature is `renderChart(d)` where `d = { dates, prices, scores }` — no longer takes the full asset object
- Uses `BY_ID[currentId]` (global state) for display name and accent color
- `zoneBandsPlugin` draws 5 coloured rectangles on the `yScore` axis before each frame
- Score line `borderWidth` increased from 1.5 to 2
- `plugins: [zoneBandsPlugin]` added at the chart level (not inside `options`)

- [ ] **Step 3: Update renderAsset to sync pills and pass sliced data**

Inside `renderAsset(a)`, find:

```js
      renderChart(a);
```

Replace it with:

```js
      ['6m','1y','2y','all'].forEach(function (k) {
        document.getElementById('cw-' + k).classList.toggle('active', k === chartWindow);
      });
      renderChart(sliceChartData(a.chart, chartWindow));
```

- [ ] **Step 4: Build**

```
python scripts/build_dashboard.py
```

Expected: `Dashboard written to docs/index.html (... bytes; 2 asset(s))`

- [ ] **Step 5: Full browser verification checklist**

Open `docs/index.html` in a browser. Check every item:

**Default state:**
- [ ] Chart shows ~1 year of data (not all history from 2010) — roughly 52 weekly bars visible
- [ ] `1Y` pill is highlighted white, the other three are grey
- [ ] Score zone bands are visible: faint red at bottom of score axis, fading through orange/grey to green at top
- [ ] Score line (`#4dd0a7` teal) reads clearly against the bands
- [ ] Price line still visible (orange/accent colour)
- [ ] Chart legend shows two entries: asset name price + "Composite Score" — no extra band entries

**Window switching:**
- [ ] Clicking `6M` shows ~6 months, pill goes white, 1Y goes grey
- [ ] Clicking `2Y` shows ~2 years
- [ ] Clicking `All` shows full history from 2010
- [ ] Clicking `1Y` returns to ~1 year view
- [ ] Zone bands are visible in every window

**Persistence:**
- [ ] Refresh page — selected window is restored (localStorage `kairos-chart-window`)

**Asset switch:**
- [ ] Clicking the second asset chip: chart updates with that asset's data in the current window, correct pill stays active

**Regression checks:**
- [ ] Spectrum gauge, chips, trend sparkline, breakdown panel all still render correctly
- [ ] Signal table rows all render
- [ ] No JS console errors (DevTools → Console)

- [ ] **Step 6: Commit**

```
git add templates/dashboard.html.j2
git commit -m "feat: add chart window pills and score zone bands"
```

---

### Task 3: Rebuild, test, push

**Files:**
- `data/bitcoin_score.json`, `data/ethereum_score.json`, `docs/index.html` (regenerated)

- [ ] **Step 1: Full rebuild**

```
python scripts/score.py && python scripts/build_dashboard.py
```

Expected:
```
Scoring Bitcoin...
  bitcoin: XX.X/100 — ... (sell: ..., spectrum: ... — ...)
Scoring Ethereum...
  ethereum: XX.X/100 — ...
Dashboard written to docs/index.html (... bytes; 2 asset(s))
```

- [ ] **Step 2: Run tests**

```
python -m pytest tests/ -q
```

Expected: all tests pass (107 tests). If any fail, fix before committing.

- [ ] **Step 3: Commit data + built HTML**

```
git add data/bitcoin_score.json data/ethereum_score.json docs/index.html
git commit -m "chore: rebuild dashboard with chart window and zone bands"
```

- [ ] **Step 4: Push**

```
git push
```

Confirm GitHub Actions picks up the push and GitHub Pages deploys at https://meyogui.github.io/fbtc-timing/ in ~2 minutes.
