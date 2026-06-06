# Score Clarity UI Redesign

## Problem

The dashboard displays three numbers without explaining their relationship:

- **Spectrum position** (e.g. 83.1) — the combined verdict, shown as the chip score and gauge cursor
- **Buy composite** (e.g. 66.2) — the weighted average of buy-side signals, shown in a "BUY SIGNAL" box
- **Sell composite** (e.g. 0.0) — the weighted average of sell-side signals, shown in a "SELL SIGNAL" box

A first-time viewer sees "STRONG BUY" at 83.1 and "BUY SIGNAL 66.2 — BUY" below it and doesn't know which is the verdict or how they relate. The formula `50 + (buy − sell) / 2 = spectrum` is invisible.

## Design Decisions

1. **Spectrum is the single headline verdict.** The big label (STRONG BUY), the cursor (83.1), and the asset chips all already use `spectrum_pos` / `spectrum_verdict`. No competing number is shown by default.

2. **Buy composite and sell composite become a collapsible breakdown.** A "▸ How is 83.1 calculated?" toggle below the spectrum gauge expands to show the formula and both inputs. Hidden by default, available on demand.

3. **Layout within the breakdown: sell left, buy right.** This mirrors the gauge direction — red/sell on the left, green/buy on the right. A mini spectrum strip inside the panel reinforces the orientation.

4. **Labels renamed:** "Sell signal" / "Buy signal" → "Sell pressure" / "Buy pressure". These are inputs to the spectrum, not verdicts. The old labels implied they were at the same level as the final verdict.

5. **Sell pressure shows "LOW — inactive" when 0.** At 0.0 the sell side isn't pulling the gauge. The sub-label makes this explicit so users understand the cursor is purely driven by buy pressure.

6. **Signal table, chart, chips, trend: unchanged.** These are already clear and are not sources of confusion.

## Scope

Template-only change. No Python scripts, data files, or tests are affected.

## Visual Reference

Approved mockup: `.superpowers/brainstorm/897-1780764669/content/full-dashboard-v2.html`

## Exact HTML Changes (templates/dashboard.html.j2)

### Remove

The `.score-row` div (two side-by-side boxes):

```html
<div class="score-row">
  <div class="score-half score-half-l"> … Sell signal … </div>
  <div class="score-half score-half-r"> … Buy signal … </div>
</div>
```

### Add after `.spectrum-wrap`

```html
<!-- Collapsible breakdown -->
<div class="breakdown-toggle" id="breakdown-toggle"
     onclick="toggleBreakdown()">
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
    <!-- LEFT: Sell pressure -->
    <div class="bk-box">
      <div class="bk-lbl bk-lbl-sell">Sell pressure</div>
      <div class="bk-val" id="bk-sell-score"></div>
      <div class="bk-sub" id="bk-sell-verdict"></div>
    </div>
    <!-- CENTRE: formula -->
    <div class="bk-formula" id="bk-formula"></div>
    <!-- RIGHT: Buy pressure -->
    <div class="bk-box">
      <div class="bk-lbl bk-lbl-buy">Buy pressure</div>
      <div class="bk-val" id="bk-buy-score"></div>
      <div class="bk-sub" id="bk-buy-verdict"></div>
    </div>
  </div>
  <hr class="bk-divider">
  <div class="bk-hint" id="bk-hint"></div>
</div>
```

### New CSS classes

```css
/* breakdown toggle */
.breakdown-toggle {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  margin-top: 1rem; font-size: 0.7rem; color: #3a3a3a;
  border: 1px solid #232323; border-radius: 6px;
  padding: 0.4rem 0.75rem; cursor: pointer; background: #1a1a1a;
  transition: color .15s, border-color .15s; user-select: none;
}
.breakdown-toggle:hover, .breakdown-toggle.open { color: #555; border-color: #333; }

/* breakdown panel */
.breakdown-panel { display: none; margin-top: 0.6rem; padding: 0.9rem; background: #111; border-radius: 8px; border: 1px solid #232323; }
.breakdown-panel.open { display: block; }

/* mini gauge strip */
.bk-mini-gauge { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin-bottom: 0.75rem; }
.bk-mg-tp   { flex: 20; background: #ff525230; }
.bk-mg-sell { flex: 20; background: #ff980028; }
.bk-mg-hold { flex: 20; background: #ffffff10; }
.bk-mg-buy  { flex: 20; background: #00c85328; }
.bk-mg-sbuy { flex: 20; background: #00e67630; }

/* grid */
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

### Remove stale CSS

Remove the following classes (no longer rendered):
`.score-row`, `.score-half`, `.score-half-l`, `.score-half-r`, `.sh-label`, `.sh-label-sell`, `.sh-label-buy`, `.sh-score`, `.sh-verdict`

### New JS: `toggleBreakdown()`

The toggle stores the spectrum score in a `data-score` attribute set by `renderAsset()`, so it never needs to read a live DOM span.

```js
function toggleBreakdown() {
  var t = document.getElementById('breakdown-toggle');
  var p = document.getElementById('breakdown-panel');
  var isOpen = p.classList.toggle('open');
  t.classList.toggle('open', isOpen);
  var arrow = isOpen ? '&#9663;' : '&#9657;';
  t.innerHTML = arrow + ' How is ' + t.getAttribute('data-score') + ' calculated?';
}
window.toggleBreakdown = toggleBreakdown;
```

### Update `renderAsset()` — remove old, add new

Remove:
```js
// sell / buy score boxes (old)
var sellScore = document.getElementById('sell-score');
sellScore.textContent = a.sell_composite.toFixed(1);
sellScore.style.color = a.sell_composite >= 25 ? '#ff9800' : '#ff5252';
document.getElementById('sell-verdict').textContent = a.sell_verdict;

var buyScore = document.getElementById('buy-score');
buyScore.textContent = a.composite.toFixed(1);
buyScore.style.color = zoneColor(a.composite);
document.getElementById('buy-verdict').textContent = a.verdict;
```

Add:
```js
// breakdown panel
// set data-score on toggle (used by toggleBreakdown to rebuild its label)
var toggle = document.getElementById('breakdown-toggle');
toggle.setAttribute('data-score', a.spectrum_pos.toFixed(1));
toggle.innerHTML = '&#9657; How is ' + a.spectrum_pos.toFixed(1) + ' calculated?';
var sellVal = document.getElementById('bk-sell-score');
sellVal.textContent = a.sell_composite.toFixed(1);
sellVal.style.color = a.sell_composite >= 25 ? '#ff9800' : '#ff5252';
var sellSub = a.sell_composite === 0
  ? 'LOW — inactive'
  : a.sell_verdict;
document.getElementById('bk-sell-verdict').textContent = sellSub;
var buyVal = document.getElementById('bk-buy-score');
buyVal.textContent = a.composite.toFixed(1);
buyVal.style.color = zoneColor(a.composite);
document.getElementById('bk-buy-verdict').textContent = a.verdict;
document.getElementById('bk-formula').innerHTML =
  '50 + (' + a.composite.toFixed(1) + ' − ' + a.sell_composite.toFixed(1) + ') / 2'
  + '<br>= <strong style="color:' + a.score_color + '">' + a.spectrum_pos.toFixed(1) + '</strong>';
var hint = a.sell_composite < 25
  ? ‘Sell pressure only pulls the gauge left when ≥ 25. At ‘ + a.sell_composite.toFixed(1) + ‘ there is no headwind — buy pressure drives the position.’
  : ‘Both buy and sell pressure are active. The gauge position reflects the net signal.’;
document.getElementById('bk-hint').textContent = hint;

// reset panel closed on asset switch (toggle label already rewritten above)
document.getElementById('breakdown-panel').classList.remove('open');
document.getElementById('breakdown-toggle').classList.remove('open');
```

## Out of Scope

- No changes to score.py, build_dashboard.py, backtest.py, or any other Python script
- No changes to data files
- No new tests required (template-only, no logic change)
- Signal table, chart, methodology accordion, chips, trend, sparkline: untouched
