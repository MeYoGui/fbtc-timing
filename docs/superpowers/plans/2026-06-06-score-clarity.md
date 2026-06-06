# Score Clarity UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the always-visible sell/buy score boxes with a single collapsible "How is X calculated?" breakdown panel, making the spectrum position the unambiguous headline verdict.

**Architecture:** Template-only change to `templates/dashboard.html.j2`. No Python, no data files, no tests. Three passes: (1) remove old CSS + HTML + JS, (2) add new CSS + HTML, (3) add new JS and wire renderAsset(). Build with `python scripts/build_dashboard.py` after each task to catch regressions early. Verification is visual — open `docs/index.html` in a browser.

**Tech Stack:** HTML, CSS, vanilla JS, Jinja2 template (static — Jinja vars are only `{{ assets_json }}`, `{{ updated_at }}`, `{{ default_asset }}` and are not touched).

---

### Task 1: Remove old sell/buy score boxes

**Files:**
- Modify: `templates/dashboard.html.j2`

This task removes three things: the 9 stale CSS classes, the `.score-row` HTML div, and the 10-line JS block in `renderAsset()` that wrote to the now-removed DOM elements. After this task the sell/buy boxes simply no longer exist.

- [ ] **Step 1: Remove the 9 stale CSS classes**

Inside the `<style>` block, find and delete these 9 lines (they appear together after `.distance`):

```css
    /* sell / buy score boxes */
    .score-row { display: flex; gap: 1px; margin-top: 1.25rem; }
    .score-half { flex: 1; padding: 0.75rem 1rem; }
    .score-half-l { border-radius: 8px 0 0 8px; background: #ff525210; border: 1px solid #ff525220; }
    .score-half-r { border-radius: 0 8px 8px 0; background: #00e67610; border: 1px solid #00e67620; }
    .sh-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; margin-bottom: 4px; }
    .sh-label-sell { color: #ff525299; }
    .sh-label-buy  { color: #00e67699; }
    .sh-score { font-size: 1.6rem; font-weight: 800; line-height: 1; }
    .sh-verdict { font-size: 0.68rem; color: #555; margin-top: 3px; }
```

Replace those 9 lines with nothing (delete them entirely).

- [ ] **Step 2: Remove the score-row HTML**

In the HTML body, find and delete this block (it appears after the closing `</div>` of `.spectrum-wrap`):

```html
    <div class="score-row">
      <div class="score-half score-half-l">
        <div class="sh-label sh-label-sell">Sell signal</div>
        <div class="sh-score" id="sell-score"></div>
        <div class="sh-verdict" id="sell-verdict"></div>
      </div>
      <div class="score-half score-half-r">
        <div class="sh-label sh-label-buy">Buy signal</div>
        <div class="sh-score" id="buy-score"></div>
        <div class="sh-verdict" id="buy-verdict"></div>
      </div>
    </div>
```

Delete the entire block.

- [ ] **Step 3: Remove old JS from renderAsset()**

Inside `renderAsset(a)`, find and delete this block:

```js
      // sell / buy score boxes
      var sellScore = document.getElementById('sell-score');
      sellScore.textContent = a.sell_composite.toFixed(1);
      sellScore.style.color = a.sell_composite >= 25 ? '#ff9800' : '#ff5252';
      document.getElementById('sell-verdict').textContent = a.sell_verdict;

      var buyScore = document.getElementById('buy-score');
      buyScore.textContent = a.composite.toFixed(1);
      buyScore.style.color = zoneColor(a.composite);
      document.getElementById('buy-verdict').textContent = a.verdict;
```

Delete those 10 lines entirely.

- [ ] **Step 4: Build and verify no errors**

```bash
python scripts/build_dashboard.py
```

Expected output:
```
Dashboard written to docs/index.html (... bytes; 2 asset(s))
```

Open `docs/index.html` in a browser. Verify:
- Page loads without JS console errors
- Spectrum gauge, chips, trend, signal table all render correctly
- The sell/buy boxes are gone (blank space where they were is fine — we'll fill it in Task 2)

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html.j2
git commit -m "refactor: remove always-visible sell/buy score boxes from dashboard"
```

---

### Task 2: Add breakdown panel CSS and HTML

**Files:**
- Modify: `templates/dashboard.html.j2`

This task adds the visual skeleton of the breakdown panel. After this task the toggle button and panel exist in the DOM — they just won't be wired to live data yet (JS comes in Task 3).

- [ ] **Step 1: Add new breakdown CSS**

Inside the `<style>` block, add the following block immediately before the closing `</style>` tag (i.e., after the last existing CSS rule `.site-footer a:hover { color: #888; }`):

```css
    /* ── collapsible breakdown ── */
    .breakdown-toggle {
      display: flex; align-items: center; justify-content: center; gap: 5px;
      margin-top: 1rem; font-size: 0.7rem; color: #3a3a3a;
      border: 1px solid #232323; border-radius: 6px;
      padding: 0.4rem 0.75rem; cursor: pointer; background: #1a1a1a;
      transition: color .15s, border-color .15s; user-select: none;
    }
    .breakdown-toggle:hover, .breakdown-toggle.open { color: #555; border-color: #333; }
    .breakdown-panel { display: none; margin-top: 0.6rem; padding: 0.9rem; background: #111; border-radius: 8px; border: 1px solid #232323; }
    .breakdown-panel.open { display: block; }
    .bk-mini-gauge { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin-bottom: 0.75rem; }
    .bk-mg-tp   { flex: 20; background: #ff525230; }
    .bk-mg-sell { flex: 20; background: #ff980028; }
    .bk-mg-hold { flex: 20; background: #ffffff10; }
    .bk-mg-buy  { flex: 20; background: #00c85328; }
    .bk-mg-sbuy { flex: 20; background: #00e67630; }
    .bk-grid { display: grid; grid-template-columns: 1fr auto 1fr; gap: 0.5rem; align-items: center; }
    .bk-box { text-align: center; }
    .bk-lbl { font-size: 0.58rem; text-transform: uppercase; letter-spacing: 0.07em; color: #3a3a3a; margin-bottom: 3px; }
    .bk-lbl-sell { color: #ff525266; }
    .bk-lbl-buy  { color: #00c85366; }
    .bk-val { font-size: 1.25rem; font-weight: 800; line-height: 1; }
    .bk-sub { font-size: 0.62rem; color: #3a3a3a; margin-top: 2px; }
    .bk-formula { font-size: 0.65rem; color: #333; text-align: center; line-height: 1.6; }
    .bk-divider { border: none; border-top: 1px solid #1e1e1e; margin: 0.7rem 0; }
    .bk-hint { font-size: 0.62rem; color: #2e2e2e; line-height: 1.5; text-align: center; }
```

- [ ] **Step 2: Add breakdown HTML after the spectrum wrap**

In the HTML body, find the closing `</div>` of `.spectrum-wrap` followed by `<div id="trend-delta"`:

```html
    </div>

    <div id="trend-delta" class="trend-delta"></div>
```

Insert the breakdown toggle and panel between the two (after `</div>`, before `<div id="trend-delta"`):

```html
    </div>

    <div class="breakdown-toggle" id="breakdown-toggle" onclick="toggleBreakdown()">
      &#9657; How is <span id="breakdown-score"></span> calculated?
    </div>
    <div class="breakdown-panel" id="breakdown-panel">
      <div class="bk-mini-gauge">
        <div class="bk-mg-tp"></div>
        <div class="bk-mg-sell"></div>
        <div class="bk-mg-hold"></div>
        <div class="bk-mg-buy"></div>
        <div class="bk-mg-sbuy"></div>
      </div>
      <div class="bk-grid">
        <div class="bk-box">
          <div class="bk-lbl bk-lbl-sell">Sell pressure</div>
          <div class="bk-val" id="bk-sell-score"></div>
          <div class="bk-sub" id="bk-sell-verdict"></div>
        </div>
        <div class="bk-formula" id="bk-formula"></div>
        <div class="bk-box">
          <div class="bk-lbl bk-lbl-buy">Buy pressure</div>
          <div class="bk-val" id="bk-buy-score"></div>
          <div class="bk-sub" id="bk-buy-verdict"></div>
        </div>
      </div>
      <hr class="bk-divider">
      <div class="bk-hint" id="bk-hint"></div>
    </div>

    <div id="trend-delta" class="trend-delta"></div>
```

- [ ] **Step 3: Build and verify structure**

```bash
python scripts/build_dashboard.py
```

Open `docs/index.html` in a browser. Verify:
- A small grey pill reading "▸ How is calculated?" appears below the spectrum gauge (the number will be empty until Task 3 wires the JS)
- Clicking it does nothing yet (JS not wired)
- No console errors
- Trend delta, sparkline, signal table still render correctly

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html.j2
git commit -m "feat: add collapsible breakdown panel HTML and CSS to score card"
```

---

### Task 3: Wire JS — toggleBreakdown + renderAsset updates

**Files:**
- Modify: `templates/dashboard.html.j2`

This task makes everything dynamic: `toggleBreakdown()` handles open/close, and `renderAsset()` populates all breakdown elements with live asset data and resets the panel when switching assets.

- [ ] **Step 1: Add toggleBreakdown() function**

In the first `<script>` block, add `toggleBreakdown` immediately after the closing brace of `setAsset` and before `renderChips()`:

Find:
```js
    window.setAsset = setAsset;

    renderChips();
```

Insert between them:

```js
    window.setAsset = setAsset;

    function toggleBreakdown() {
      var t = document.getElementById('breakdown-toggle');
      var p = document.getElementById('breakdown-panel');
      var isOpen = p.classList.toggle('open');
      t.classList.toggle('open', isOpen);
      var arrow = isOpen ? '&#9663;' : '&#9657;';
      t.innerHTML = arrow + ' How is ' + t.getAttribute('data-score') + ' calculated?';
    }
    window.toggleBreakdown = toggleBreakdown;

    renderChips();
```

- [ ] **Step 2: Add breakdown population to renderAsset()**

In `renderAsset(a)`, find the block that starts with the spectrum verdict comment and ends just before `renderTable(a)`:

```js
      // spectrum verdict + cursor
      var sv = document.getElementById('spectrum-verdict');
```

Add the following block immediately before `renderTable(a);`:

```js
      // breakdown panel — populate and reset closed on every asset switch
      var bkToggle = document.getElementById('breakdown-toggle');
      bkToggle.setAttribute('data-score', a.spectrum_pos.toFixed(1));
      bkToggle.innerHTML = '&#9657; How is ' + a.spectrum_pos.toFixed(1) + ' calculated?';
      bkToggle.classList.remove('open');
      document.getElementById('breakdown-panel').classList.remove('open');

      var sellVal = document.getElementById('bk-sell-score');
      sellVal.textContent = a.sell_composite.toFixed(1);
      sellVal.style.color = a.sell_composite >= 25 ? '#ff9800' : '#ff5252';
      document.getElementById('bk-sell-verdict').textContent =
        a.sell_composite === 0 ? 'LOW — inactive' : a.sell_verdict;

      var buyVal = document.getElementById('bk-buy-score');
      buyVal.textContent = a.composite.toFixed(1);
      buyVal.style.color = zoneColor(a.composite);
      document.getElementById('bk-buy-verdict').textContent = a.verdict;

      document.getElementById('bk-formula').innerHTML =
        '50 + (' + a.composite.toFixed(1) + ' − ' + a.sell_composite.toFixed(1) + ') / 2'
        + '<br>= <strong style="color:' + a.score_color + '">' + a.spectrum_pos.toFixed(1) + '</strong>';

      document.getElementById('bk-hint').textContent = a.sell_composite < 25
        ? 'Sell pressure only pulls the gauge left when ≥ 25. At '
          + a.sell_composite.toFixed(1) + ' there is no headwind — buy pressure drives the position.'
        : 'Both buy and sell pressure are active. The gauge position reflects the net signal.';
```

- [ ] **Step 3: Build**

```bash
python scripts/build_dashboard.py
```

Expected output:
```
Dashboard written to docs/index.html (... bytes; 2 asset(s))
```

- [ ] **Step 4: Full browser verification checklist**

Open `docs/index.html` in a browser. Check every item:

**Default state (collapsed):**
- [ ] Toggle pill reads "▸ How is 83.1 calculated?" (number matches the spectrum cursor)
- [ ] No breakdown panel visible below the gauge

**Expand:**
- [ ] Clicking the pill opens the panel and changes arrow to ▾
- [ ] Mini spectrum strip appears across the top of the panel (5 colour segments: red → orange → grey → green → bright green)
- [ ] Left column: "SELL PRESSURE" label in red-tint, value in red (e.g. 0.0), sub-label "LOW — inactive"
- [ ] Centre: formula e.g. `50 + (66.2 − 0.0) / 2` on line 1, `= 83.1` in green on line 2
- [ ] Right column: "BUY PRESSURE" label in green-tint, value in green (e.g. 66.2), sub-label e.g. "BUY"
- [ ] Hint text: "Sell pressure only pulls the gauge left when ≥ 25. At 0.0 there is no headwind — buy pressure drives the position."
- [ ] Divider line between grid and hint

**Collapse:**
- [ ] Clicking again closes the panel and restores ▸

**Asset switch (if Ethereum chip is present):**
- [ ] Clicking Ethereum chip: breakdown panel collapses, toggle updates to "▸ How is 87.7 calculated?"
- [ ] Expanding shows Ethereum's values (different buy/sell composites)

**Regression checks:**
- [ ] Spectrum gauge cursor and label still correct
- [ ] Trend delta and sparkline still render
- [ ] Signal table still renders all rows with range bars
- [ ] Chart still renders
- [ ] No JS console errors (open DevTools → Console tab)

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html.j2
git commit -m "feat: wire breakdown toggle JS and renderAsset population"
```

---

### Task 4: Rebuild, push

**Files:**
- `data/bitcoin_score.json`, `data/ethereum_score.json`, `docs/index.html` (regenerated)

- [ ] **Step 1: Final build**

```bash
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

- [ ] **Step 2: Run tests to confirm no regressions**

```bash
python -m pytest tests/ -q
```

Expected: all 107 tests pass.

- [ ] **Step 3: Commit data + built HTML**

```bash
git add data/bitcoin_score.json data/ethereum_score.json docs/index.html
git commit -m "chore: rebuild dashboard with score clarity redesign"
```

- [ ] **Step 4: Push**

```bash
git push
```

Confirm GitHub Actions picks up the push and GitHub Pages deploys (check https://meyogui.github.io/fbtc-timing/ in ~2 minutes).
