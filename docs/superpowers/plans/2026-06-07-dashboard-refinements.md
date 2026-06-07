# Dashboard Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply seven UX refinements to the redesigned Kairos dashboard (price on cards, white score needle, "STRONG SELL" label, score tooltips, no "LIVE", a details score-history block, and AVOID/WAIT/INVEST signal gauges).

**Architecture:** Every change is to the single generated template `templates/dashboard.html.j2`; `docs/index.html` is regenerated with `python scripts/build_dashboard.py`. All data needed already exists in the embedded `ASSETS` blob — no Python, build-script, data, or test changes. Per the spec at `docs/superpowers/specs/2026-06-07-dashboard-refinements-design.md`.

**Tech Stack:** Jinja2 template, vanilla JS, Tailwind (CDN), Chart.js (CDN). Verification is build success + deterministic content checks per task, then one Playwright visual pass at the end (no JS unit-test framework exists in this repo).

---

## Conventions for every task

- Work from repo root `C:\Users\guill\Workspace\fbtc-timing` on branch `feat/new-design-redesign`.
- After editing the template, ALWAYS run `python scripts/build_dashboard.py` (expected tail: `Dashboard written to docs/index.html (... bytes; 2 asset(s))`). The generated `docs/index.html` is committed alongside the template.
- `docs/index.html` is generated — never hand-edit it.
- The main `<script>` in the template is a classic script, so top-level `function` declarations are global and reachable from inline `onclick` handlers.

---

## Task 1: Move price onto each card (#1)

**Files:**
- Modify: `templates/dashboard.html.j2` (app bar markup, `cardHTML`, `renderIndexHeader`)

- [ ] **Step 1: Remove the price from the top app bar**

In the index app bar, replace:

```html
      <div class="font-data-sm text-data-sm text-on-surface-variant flex flex-col items-end leading-tight">
        <span class="text-cyber-emerald" id="idx-btc-price">—</span>
        <span class="text-[10px] opacity-50" id="idx-updated">—</span>
      </div>
```

with:

```html
      <div class="font-data-sm text-data-sm text-on-surface-variant flex items-center">
        <span class="text-[10px] opacity-50" id="idx-updated">—</span>
      </div>
```

- [ ] **Step 2: Add the price line under the coin name in `cardHTML`**

Replace this line:

```javascript
        +   '<div class="flex items-center gap-2 text-on-surface font-headline-lg-mobile text-2xl">' + a.short_label + '</div>'
```

with:

```javascript
        +   '<div class="flex flex-col">'
        +     '<div class="flex items-center gap-2 text-on-surface font-headline-lg-mobile text-2xl">' + a.short_label + '</div>'
        +     '<span class="font-data-sm text-data-sm text-cyber-emerald mt-1">' + a.price_unit + a.price.toLocaleString() + '</span>'
        +   '</div>'
```

- [ ] **Step 3: Drop the now-removed `idx-btc-price` lookup in `renderIndexHeader`**

Replace:

```javascript
    function renderIndexHeader() {
      const first = BY_ID[DEFAULT_ASSET] || ASSETS[0];
      document.getElementById('idx-btc-price').textContent = first.price_unit + first.price.toLocaleString();
      document.getElementById('idx-updated').textContent = 'Updated ' + UPDATED_AT;
    }
```

with:

```javascript
    function renderIndexHeader() {
      document.getElementById('idx-updated').textContent = 'Updated ' + UPDATED_AT;
    }
```

- [ ] **Step 4: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: `... 2 asset(s)`

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('idx-btc-price' not in h, 'mt-1\">' + chr(39) + ' + a.price_unit' in h or 'a.price_unit + a.price.toLocaleString()' in h)"`
Expected: `True True`

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: show per-coin price on each welcome card"
```

---

## Task 2: "TP" → "STRONG SELL" everywhere it shows (#7)

**Files:**
- Modify: `templates/dashboard.html.j2` (`ZONE_LABELS`, new `displayVerdict`, `cardHTML`, `openDetails`)

- [ ] **Step 1: Rename the leftmost zone label**

Replace:

```javascript
    const ZONE_LABELS = ['TP', 'Sell', 'Hold', 'Buy', 'Strong Buy'];
```

with:

```javascript
    const ZONE_LABELS = ['Strong Sell', 'Sell', 'Hold', 'Buy', 'Strong Buy'];
```

- [ ] **Step 2: Add a display-only verdict mapping**

Replace:

```javascript
    const ZONE_COLORS = ['#FF3B30', '#ff9800', '#D0D0D0', '#00C853', '#00ff88'];
```

with:

```javascript
    const ZONE_COLORS = ['#FF3B30', '#ff9800', '#D0D0D0', '#00C853', '#00ff88'];
    // Display-only: the lowest composite band is scored "TAKE PROFIT" but shown as "STRONG SELL".
    function displayVerdict(v) { return v === 'TAKE PROFIT' ? 'STRONG SELL' : v; }
```

- [ ] **Step 3: Use it for the card verdict**

Replace:

```javascript
        +       '<span class="text-[11px] font-label-caps tracking-widest font-bold opacity-90" style="color:' + col + '">' + a.spectrum_verdict + '</span>'
```

with:

```javascript
        +       '<span class="text-[11px] font-label-caps tracking-widest font-bold opacity-90" style="color:' + col + '">' + displayVerdict(a.spectrum_verdict) + '</span>'
```

- [ ] **Step 4: Use it for the details hero verdict**

Replace:

```javascript
      vEl.textContent = a.spectrum_verdict;
```

with:

```javascript
      vEl.textContent = displayVerdict(a.spectrum_verdict);
```

- [ ] **Step 5: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: `... 2 asset(s)`

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('Strong Sell' in h, \"'TP'\" not in h, 'displayVerdict' in h)"`
Expected: `True True True`

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: relabel take-profit zone as STRONG SELL in UI"
```

---

## Task 3: White score needle on the welcome-card range (#6)

**Files:**
- Modify: `templates/dashboard.html.j2` (`spectrumBandHTML`)

- [ ] **Step 1: Overlay the needle while keeping the existing zone coloring**

Replace:

```javascript
      return '<div class="relative w-full h-1.5 bg-surface-variant rounded-full overflow-hidden flex">' + segs + '</div>'
        + '<div class="flex justify-between text-[9px] font-label-caps uppercase tracking-tighter mt-1">' + labels + '</div>';
```

with:

```javascript
      return '<div class="relative w-full">'
        + '<div class="relative w-full h-1.5 bg-surface-variant rounded-full overflow-hidden flex">' + segs + '</div>'
        + '<div class="absolute" style="top:50%;left:' + a.spectrum_pos + '%;transform:translate(-50%,-50%);width:3px;height:12px;background:#fff;border-radius:2px;box-shadow:0 0 9px rgba(255,255,255,0.95);"></div>'
        + '</div>'
        + '<div class="flex justify-between text-[9px] font-label-caps uppercase tracking-tighter mt-1">' + labels + '</div>';
```

- [ ] **Step 2: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: `... 2 asset(s)`

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print(\"left:' + a.spectrum_pos + '%\" in h, 'box-shadow:0 0 9px rgba(255,255,255,0.95)' in h)"`
Expected: `True True`

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: add white score needle to welcome-card range"
```

---

## Task 4: Score-history tooltips (#2) + reusable bar renderer

This refactors the card mini-bars into a reusable `sparkBarsHTML` (also used by Task 7) and adds an on-hover/on-tap tooltip showing `"<date> — <score>"` colored by zone.

**Files:**
- Modify: `templates/dashboard.html.j2` (`<style>`, `miniBarsHTML` → `sparkBarsHTML` + `toggleTip`)

- [ ] **Step 1: Add tooltip CSS**

Replace:

```css
    .hidden-view { display: none !important; }
```

with:

```css
    .spark-bar { position: relative; }
    .spark-bar .spark-tip { display: none; position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%); background: #161616; border: 1px solid #2a2a2a; border-radius: 5px; padding: 3px 8px; white-space: nowrap; font-size: 11px; font-family: 'JetBrains Mono', monospace; pointer-events: none; z-index: 30; }
    .spark-bar:hover .spark-tip, .spark-bar.tip-open .spark-tip { display: block; }
    .hidden-view { display: none !important; }
```

- [ ] **Step 2: Replace `miniBarsHTML` with `sparkBarsHTML` + `toggleTip` + a thin `miniBarsHTML` wrapper**

Replace:

```javascript
    function miniBarsHTML(a) {
      const sp = a.trend[timeframe].spark;
      const scores = sp.map(p => p.score);
      const mx = Math.max.apply(null, scores);
      const mn = Math.min.apply(null, scores) - 3;
      const span = (mx - mn) || 1;
      return sp.map(function (p, i) {
        const h = Math.max(Math.round(((p.score - mn) / span) * 100), 12);
        const last = i === sp.length - 1;
        const bg = last ? 'background:' + zoneColor(p.score) + ';box-shadow:0 0 8px rgba(0,255,136,0.6);' : 'background:#222222;';
        return '<div class="w-full rounded-sm" style="height:' + h + '%;' + bg + '"></div>';
      }).join('');
    }
```

with:

```javascript
    // Shared score-history bars with a date+score tooltip (hover on desktop, tap on mobile).
    function sparkBarsHTML(spark) {
      const scores = spark.map(p => p.score);
      const mx = Math.max.apply(null, scores);
      const mn = Math.min.apply(null, scores) - 3;
      const span = (mx - mn) || 1;
      return spark.map(function (p, i) {
        const h = Math.max(Math.round(((p.score - mn) / span) * 100), 12);
        const col = zoneColor(p.score);
        const last = i === spark.length - 1;
        const bg = last ? 'background:' + col + ';box-shadow:0 0 8px rgba(0,255,136,0.6);' : 'background:#222222;';
        return '<div class="spark-bar w-full rounded-sm" style="height:' + h + '%;' + bg + '" onclick="toggleTip(event, this)">'
          + '<span class="spark-tip" style="color:' + col + '">' + p.label + ' — ' + p.score.toFixed(1) + '</span></div>';
      }).join('');
    }
    function toggleTip(ev, el) { ev.stopPropagation(); el.classList.toggle('tip-open'); }

    function miniBarsHTML(a) {
      return sparkBarsHTML(a.trend[timeframe].spark);
    }
```

- [ ] **Step 3: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: `... 2 asset(s)`

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('sparkBarsHTML' in h, 'spark-tip' in h, 'toggleTip(event, this)' in h)"`
Expected: `True True True`

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: date+score tooltips on score-history bars"
```

---

## Task 5: Remove "LIVE" from the details header (#3)

**Files:**
- Modify: `templates/dashboard.html.j2` (details context header)

- [ ] **Step 1: Delete the dot + LIVE spans**

Replace:

```html
          <div class="flex items-center gap-2 mt-1">
            <span class="font-label-caps text-label-caps text-on-surface-variant" id="detail-subtitle">DETAILS</span>
            <span class="h-1 w-1 bg-cyber-emerald rounded-full shadow-[0_0_5px_#00ff88]"></span>
            <span class="font-data-sm text-data-sm text-cyber-emerald">LIVE</span>
          </div>
```

with:

```html
          <div class="flex items-center gap-2 mt-1">
            <span class="font-label-caps text-label-caps text-on-surface-variant" id="detail-subtitle">DETAILS</span>
          </div>
```

- [ ] **Step 2: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: `... 2 asset(s)`

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('>LIVE<' not in h, 'shadow-[0_0_5px_#00ff88]' not in h)"`
Expected: `True True`

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: remove LIVE indicator from details header"
```

---

## Task 6: Signal gauges — AVOID/WAIT/INVEST, Layout B (#5)

Rewrites the non-empty branch of `metricCardHTML` to use the real per-signal zone widths, an inline label row (zone words + gating values at their positions), divider ticks, and the white needle. Reading color is unchanged (`metricColor`).

**Files:**
- Modify: `templates/dashboard.html.j2` (`metricCardHTML`)

- [ ] **Step 1: Replace the gauge markup**

Replace:

```javascript
      const col = metricColor(b.status_class);
      return '<div class="bg-surface-charcoal border border-border-subtle rounded-xl p-stack-md flex flex-col hover:border-cyber-emerald/30 transition-colors group">'
        + '<div class="flex justify-between items-start mb-6 gap-2">'
        +   '<span class="font-label-caps text-label-caps text-on-surface-variant group-hover:text-on-surface transition-colors">' + sig.display_name + '</span>'
        +   '<span class="font-data-lg text-data-lg text-right" style="color:' + col + ';text-shadow:0 0 8px ' + col + '33;">' + sig.reading + '</span>'
        + '</div>'
        + '<div class="mt-auto w-full">'
        +   '<div class="flex justify-between font-label-caps text-label-caps text-surface-variant mb-1 text-[9px]"><span>TAKE PROFIT</span><span>STRONG BUY</span></div>'
        +   '<div class="h-1.5 w-full bg-surface-container-highest rounded-full relative overflow-hidden flex">'
        +     '<div class="h-full bg-sell-urgent/20 w-1/4"></div>'
        +     '<div class="h-full bg-surface-variant w-1/2"></div>'
        +     '<div class="h-full bg-cyber-emerald/20 w-1/4"></div>'
        +     '<div class="absolute top-0 bottom-0 w-1" style="left:' + b.cursor_pct + '%;background:' + col + ';box-shadow:0 0 5px ' + col + ';"></div>'
        +   '</div>'
        + '</div></div>';
```

with:

```javascript
      const col = metricColor(b.status_class);
      return '<div class="bg-surface-charcoal border border-border-subtle rounded-xl p-stack-md flex flex-col hover:border-cyber-emerald/30 transition-colors group">'
        + '<div class="flex justify-between items-start mb-6 gap-2">'
        +   '<span class="font-label-caps text-label-caps text-on-surface-variant group-hover:text-on-surface transition-colors">' + sig.display_name + '</span>'
        +   '<span class="font-data-lg text-data-lg text-right" style="color:' + col + ';text-shadow:0 0 8px ' + col + '33;">' + sig.reading + '</span>'
        + '</div>'
        + '<div class="mt-auto w-full">'
        +   '<div class="relative h-3.5 mb-1 text-[8px] font-label-caps uppercase tracking-tight">'
        +     '<span class="absolute left-0" style="color:#ff8a80">Avoid</span>'
        +     '<span class="absolute -translate-x-1/2" style="left:' + b.thresh_avoid_pct + '%;color:#cfcfcf">' + b.thresh_avoid_lbl + '</span>'
        +     '<span class="absolute -translate-x-1/2" style="left:50%;color:#9a9a9a">Wait</span>'
        +     '<span class="absolute -translate-x-1/2" style="left:' + b.thresh_invest_pct + '%;color:#cfcfcf">' + b.thresh_invest_lbl + '</span>'
        +     '<span class="absolute right-0" style="color:#00ff88">Invest</span>'
        +   '</div>'
        +   '<div class="relative w-full">'
        +     '<div class="h-1.5 w-full rounded-full overflow-hidden flex">'
        +       '<div class="h-full" style="width:' + b.avoid_pct + '%;background:rgba(255,59,48,0.30)"></div>'
        +       '<div class="h-full" style="width:' + b.wait_pct + '%;background:rgba(255,255,255,0.10)"></div>'
        +       '<div class="h-full" style="width:' + b.invest_pct + '%;background:rgba(0,255,136,0.30)"></div>'
        +     '</div>'
        +     '<div class="absolute" style="top:50%;left:' + b.thresh_avoid_pct + '%;transform:translate(-50%,-50%);width:1px;height:9px;background:rgba(255,255,255,0.35)"></div>'
        +     '<div class="absolute" style="top:50%;left:' + b.thresh_invest_pct + '%;transform:translate(-50%,-50%);width:1px;height:9px;background:rgba(255,255,255,0.35)"></div>'
        +     '<div class="absolute" style="top:50%;left:' + b.cursor_pct + '%;transform:translate(-50%,-50%);width:2px;height:12px;background:#fff;border-radius:2px;box-shadow:0 0 8px rgba(255,255,255,0.95)"></div>'
        +   '</div>'
        + '</div></div>';
```

- [ ] **Step 2: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: `... 2 asset(s)`

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('>Avoid<' in h, '>Invest<' in h, 'b.thresh_avoid_lbl' in h, 'TAKE PROFIT</span><span>STRONG BUY' not in h)"`
Expected: `True True True True`

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: signal gauges with AVOID/WAIT/INVEST and threshold values"
```

---

## Task 7: Score-history block on the details view (#4)

Adds a "Score history" section (its own Day/Week/Month toggle, independent state) between the hero and the metric cards, reusing `sparkBarsHTML` from Task 4.

**Files:**
- Modify: `templates/dashboard.html.j2` (details markup, new state + render fns, `openDetails`, boot wiring)

- [ ] **Step 1: Insert the markup between the hero and the metric cards**

Replace:

```html
      </section>

      <!-- Metric Cards (rendered by renderMetricCards) -->
      <section id="metric-cards" class="px-container-padding grid grid-cols-1 md:grid-cols-3 gap-stack-md py-stack-md relative z-10"></section>
```

with:

```html
      </section>

      <!-- Score history -->
      <section class="px-container-padding pt-stack-sm pb-stack-md">
        <div class="flex justify-between items-center mb-3">
          <span class="font-label-caps text-label-caps text-on-surface">SCORE HISTORY</span>
          <div class="flex bg-surface-container-low p-0.5 rounded-full border border-border-subtle">
            <button type="button" data-dtf="day"   class="dtf-pill px-3 py-1 text-[11px] font-data-sm rounded-full uppercase tracking-wider transition-colors">Day</button>
            <button type="button" data-dtf="week"  class="dtf-pill px-3 py-1 text-[11px] font-data-sm rounded-full uppercase tracking-wider transition-colors">Week</button>
            <button type="button" data-dtf="month" class="dtf-pill px-3 py-1 text-[11px] font-data-sm rounded-full uppercase tracking-wider transition-colors">Month</button>
          </div>
        </div>
        <div id="detail-history" class="flex gap-1.5 items-end h-20"></div>
      </section>

      <!-- Metric Cards (rendered by renderMetricCards) -->
      <section id="metric-cards" class="px-container-padding grid grid-cols-1 md:grid-cols-3 gap-stack-md py-stack-md relative z-10"></section>
```

- [ ] **Step 2: Add independent state + render functions**

Replace:

```javascript
    let chartWindow = (function () {
      try { var w = localStorage.getItem('kairos-chart-window'); if (['6m','1y','2y','all'].includes(w)) return w; } catch (e) {}
      return '1y';
    })();
```

with:

```javascript
    let chartWindow = (function () {
      try { var w = localStorage.getItem('kairos-chart-window'); if (['6m','1y','2y','all'].includes(w)) return w; } catch (e) {}
      return '1y';
    })();
    let detailWindow = (function () {
      try { var w = localStorage.getItem('kairos-detail-trend-window'); if (['day','week','month'].includes(w)) return w; } catch (e) {}
      return 'day';
    })();

    function renderDetailHistory(a) {
      document.getElementById('detail-history').innerHTML = sparkBarsHTML(a.trend[detailWindow].spark);
    }

    function setDetailWindow(w) {
      detailWindow = w;
      try { localStorage.setItem('kairos-detail-trend-window', w); } catch (e) {}
      document.querySelectorAll('.dtf-pill').forEach(function (el) {
        const active = el.getAttribute('data-dtf') === w;
        el.classList.toggle('bg-on-surface', active);
        el.classList.toggle('text-deep-abyss', active);
        el.classList.toggle('font-bold', active);
        el.classList.toggle('text-on-surface-variant', !active);
      });
      if (detailId) renderDetailHistory(BY_ID[detailId]);
    }
```

- [ ] **Step 3: Render the history when details opens**

Replace:

```javascript
      renderMetricCards(a);
      showView('details');
```

with:

```javascript
      renderMetricCards(a);
      setDetailWindow(detailWindow);
      showView('details');
```

- [ ] **Step 4: Wire the Day/Week/Month pills in the boot block**

Replace:

```javascript
    document.querySelectorAll('.cw-pill').forEach(function (el) {
      el.addEventListener('click', function () { setChartWindow(el.getAttribute('data-cw')); });
    });
```

with:

```javascript
    document.querySelectorAll('.cw-pill').forEach(function (el) {
      el.addEventListener('click', function () { setChartWindow(el.getAttribute('data-cw')); });
    });
    document.querySelectorAll('.dtf-pill').forEach(function (el) {
      el.addEventListener('click', function () { setDetailWindow(el.getAttribute('data-dtf')); });
    });
```

- [ ] **Step 5: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: `... 2 asset(s)`

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('detail-history' in h, 'dtf-pill' in h, 'renderDetailHistory' in h, 'kairos-detail-trend-window' in h)"`
Expected: `True True True True`

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: score-history block with own timeframe on details view"
```

---

## Task 8: Full visual verification

No new code unless a defect is found. Confirm all seven changes render correctly together.

**Files:** none (verification only; commit a fix only if a defect is found)

- [ ] **Step 1: Sanity — Python suite still green (unchanged, but confirm)**

Run: `python -m pytest -q`
Expected: all pass (116).

- [ ] **Step 2: Serve and screenshot with Playwright**

Serve `docs/` (e.g. `python -m http.server 8765 --bind 127.0.0.1` from `docs/`, run in background), then with the Playwright MCP:
1. `browser_navigate` `http://127.0.0.1:8765/index.html`; `browser_resize` 390×844.
2. `browser_take_screenshot` (index) — verify: price under each coin name; app bar shows only KAIROS + "Updated…"; white needle on each card's range; leftmost zone label reads "Strong Sell".
3. Hover and (separately) `browser_click` a card's score-history bar — verify a tooltip "<date> — <score>" appears, colored by zone; clicking a bar does NOT open details (tap toggles the tooltip).
4. `browser_click` the Bitcoin card → details. Verify: no "LIVE"; a "SCORE HISTORY" block with Day/Week/Month pills sits above the metric cards; clicking those pills re-renders the bars independently of the welcome page; signal cards show `AVOID · <gate> · WAIT · <gate> · INVEST` with the white needle and the reading colored by state.
5. `browser_console_messages` (error) — only the expected `/fbtc-timing/` 404s; no JS errors.

- [ ] **Step 3: If a defect is found, fix in `templates/dashboard.html.j2`, rebuild, and commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "fix: <describe the visual defect corrected>"
```

If no defects: nothing to commit; task complete.

---

## Self-Review

**1. Spec coverage**
- #1 price on cards → Task 1 (app bar removal + `cardHTML` price line + `renderIndexHeader`). ✔
- #2 score tooltips (date+score, zone color, no price; tap-toggle) → Task 4 (`sparkBarsHTML`, CSS, `toggleTip`). ✔
- #3 remove LIVE → Task 5. ✔
- #4 details score-history block with own Day/Week/Month → Task 7 (markup + `detailWindow` state + `renderDetailHistory`/`setDetailWindow` + `openDetails` + boot wiring), reusing Task 4's `sparkBarsHTML`. ✔
- #5 signal gauges AVOID/WAIT/INVEST + threshold values, Layout B, real widths, needle → Task 6. ✔
- #6 white needle on card range, original coloring kept → Task 3. ✔
- #7 "TP" → "STRONG SELL" (zone label + verdict display) → Task 2. ✔
- Visual confirmation of all → Task 8. ✔

**2. Placeholder scan:** No TBD/TODO. Every code step shows the exact replacement. Task 8 verification-only is explicit.

**3. Type/name consistency:** New globals used consistently — `displayVerdict` (Task 2, used in `cardHTML` + `openDetails`), `sparkBarsHTML`/`toggleTip` (Task 4, reused in Task 7), `detailWindow`/`renderDetailHistory`/`setDetailWindow` and the `dtf-pill` / `detail-history` / `kairos-detail-trend-window` identifiers (Task 7, matching the markup). `miniBarsHTML(a)` keeps its signature (now delegating to `sparkBarsHTML`). All `bar.*` fields referenced in Task 6 (`avoid_pct`, `wait_pct`, `invest_pct`, `thresh_avoid_pct`, `thresh_invest_pct`, `thresh_avoid_lbl`, `thresh_invest_lbl`, `cursor_pct`, `status_class`) exist in the asset blob.

**Ordering note:** Task 4 must run before Task 7 (Task 7 calls `sparkBarsHTML`). Tasks 1, 2, 3, 5, 6 are independent and touch non-overlapping regions, so their relative order does not matter.
