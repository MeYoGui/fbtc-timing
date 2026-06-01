# Trend Indicators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Day / Week / Month trend layer to the Kairos dashboard — direction arrows on signals, delta line and sparkline with tooltips on the composite score card.

**Architecture:** A new `build_trend_data()` function in `build_dashboard.py` pre-computes all three windows' data (delta, sparkline, signal arrows) at build time and embeds the result as `trend_data_json` in the static HTML. A client-side JS toggle switches between windows with no network requests — the same pattern as the existing historical chart data. Template changes add the toggle, score card elements, and signal arrow column.

**Tech Stack:** Python / pandas (data), Jinja2 (template), vanilla JS + CSS (interactive toggle, sparkline tooltips)

---

## File Map

| File | What changes |
|---|---|
| `scripts/build_dashboard.py` | Add `_score_to_verdict()`, `_spark_label()`, `build_trend_data()`; call it in `main()`; pass `trend_data_json` to template |
| `templates/dashboard.html.j2` | Add CSS (toggle, delta, sparkline, arrow column); add HTML (toggle, delta line, sparkline, arrow `<td>`); add JS toggle block |
| `tests/test_build_dashboard.py` | Add tests for `build_trend_data()` |

---

## Task 1: `build_trend_data()` — Python function + tests

**Files:**
- Modify: `scripts/build_dashboard.py`
- Modify: `tests/test_build_dashboard.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_dashboard.py`:

```python
# ── build_trend_data ─────────────────────────────────────────────────────────
# Import the new function (will fail until Task 1 Step 3 is done)
from build_dashboard import build_trend_data

_SIGNAL_NAMES = ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]

def _make_signals_df(n_days: int = 400, start_score: int = 40, end_score: int = 60):
    """Minimal signals_df with linearly changing integer scores over n_days."""
    dates = pd.date_range(end="2026-05-31", periods=n_days, freq="D")
    scores = np.linspace(start_score, end_score, n_days).round().astype(int)
    data: dict = {"date": dates}
    for sig in _SIGNAL_NAMES:
        data[f"{sig}_raw"] = np.ones(n_days)
        data[sig] = scores
    return pd.DataFrame(data)

_EQUAL_WEIGHTS = {
    "signals": {sig: {"weight": 1.0} for sig in _SIGNAL_NAMES}
}


def test_trend_data_returns_all_windows():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    assert set(result.keys()) == {"day", "week", "month"}


def test_trend_each_window_has_required_keys():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        assert "delta" in result[win]
        assert "spark" in result[win]
        assert "arrows" in result[win]


def test_trend_spark_has_seven_entries():
    result = build_trend_data(_make_signals_df(n_days=400), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        assert len(result[win]["spark"]) == 7


def test_trend_spark_entry_keys():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for entry in result["day"]["spark"]:
        assert "score" in entry
        assert "label" in entry
        assert "verdict" in entry


def test_trend_arrows_cover_all_signals():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        assert set(result[win]["arrows"].keys()) == set(_SIGNAL_NAMES)


def test_trend_arrow_values_are_valid():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        for sig, val in result[win]["arrows"].items():
            assert val in (-1, 0, 1), f"{win}.{sig} arrow={val}"


def test_trend_uptrend_gives_positive_delta():
    # Scores rise 40→60 → today > yesterday
    result = build_trend_data(_make_signals_df(n_days=40, start_score=40, end_score=60), _EQUAL_WEIGHTS)
    assert result["day"]["delta"] > 0


def test_trend_downtrend_gives_negative_delta():
    # Scores fall 60→40 → today < yesterday
    result = build_trend_data(_make_signals_df(n_days=40, start_score=60, end_score=40), _EQUAL_WEIGHTS)
    assert result["day"]["delta"] < 0


def test_trend_no_prior_data_gives_zero_delta():
    # Only 1 row — no prior day to compare
    result = build_trend_data(_make_signals_df(n_days=1), _EQUAL_WEIGHTS)
    assert result["day"]["delta"] == 0.0
    assert all(v == 0 for v in result["day"]["arrows"].values())
```

Also add `import pandas as pd` and `import numpy as np` to the imports at the top of `tests/test_build_dashboard.py` (currently only `pytest`, `sys`, `pathlib`, `build_dashboard` are imported).

- [ ] **Step 2: Run tests to confirm they fail**

```
python -m pytest tests/test_build_dashboard.py -k "trend" -v
```

Expected: `ImportError: cannot import name 'build_trend_data'`

- [ ] **Step 3: Implement the function in `scripts/build_dashboard.py`**

Add these three functions right after `compute_historical_scores()` (line 109), before `build_chart_data()`:

```python
def _score_to_verdict(score: float) -> str:
    if score >= 80: return "STRONG BUY"
    if score >= 72: return "INVEST"
    if score >= 50: return "CLOSE"
    if score >= 25: return "WAIT"
    return "AVOID"


def _spark_label(date: pd.Timestamp, window: str) -> str:
    month_day = f"{date.strftime('%b')} {date.day}"
    if window == "week":
        return f"wk {month_day}"
    if window == "month":
        return date.strftime("%b %Y")
    return month_day  # day


def build_trend_data(signals_df: pd.DataFrame, weights: dict) -> dict:
    """Pre-compute Day/Week/Month trend data for embedding in the dashboard HTML.

    Returns a dict keyed by window ("day", "week", "month"), each containing:
      delta  – float, composite score change from N periods ago (positive = improving)
      spark  – list of up to 7 dicts {"score", "label", "verdict"}, oldest first
      arrows – dict signal_name -> int (1=up, 0=flat, -1=down)
    """
    df = signals_df.copy()
    df["composite_score"] = compute_historical_scores(df, weights)
    df = df.set_index("date").sort_index()

    today_composite = float(df["composite_score"].iloc[-1])
    today_date = df.index[-1]
    today_signals = {sig: int(df[sig].iloc[-1]) for sig in SIGNAL_DISPLAY}

    spark_frames = {
        "day":   df.resample("D").last().dropna(subset=["composite_score"]),
        "week":  df.resample("W").last().dropna(subset=["composite_score"]),
        "month": df.resample("ME").last().dropna(subset=["composite_score"]),
    }
    lookback_days = {"day": 1, "week": 7, "month": 30}

    result = {}
    for win in ("day", "week", "month"):
        lookback_date = today_date - pd.Timedelta(days=lookback_days[win])
        prior = df[df.index <= lookback_date]

        if len(prior) > 0:
            ref = prior.iloc[-1]
            delta = round(today_composite - float(ref["composite_score"]), 1)
            arrows = {
                sig: (1 if today_signals[sig] > int(ref[sig])
                      else -1 if today_signals[sig] < int(ref[sig])
                      else 0)
                for sig in SIGNAL_DISPLAY
            }
        else:
            delta = 0.0
            arrows = {sig: 0 for sig in SIGNAL_DISPLAY}

        spark_scores = spark_frames[win]["composite_score"].tail(7)
        spark = [
            {
                "score":   round(float(s), 1),
                "label":   _spark_label(d, win),
                "verdict": _score_to_verdict(float(s)),
            }
            for d, s in spark_scores.items()
        ]

        result[win] = {"delta": delta, "spark": spark, "arrows": arrows}

    return result
```

- [ ] **Step 4: Run trend tests to confirm they pass**

```
python -m pytest tests/test_build_dashboard.py -k "trend" -v
```

Expected: 9 tests PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```
python -m pytest -q
```

Expected: 39 passed (30 existing + 9 new).

- [ ] **Step 6: Commit**

```
git add scripts/build_dashboard.py tests/test_build_dashboard.py
git commit -m "feat: add build_trend_data() for day/week/month trend pre-computation"
```

---

## Task 2: Wire `build_trend_data()` into `main()` and verify build

**Files:**
- Modify: `scripts/build_dashboard.py` (the `main()` function only)

- [ ] **Step 1: Call `build_trend_data()` in `main()` and pass result to template**

In `main()`, add the call right after `chart_data = build_chart_data(...)` (currently line 138):

```python
    chart_data = build_chart_data(price_df, signals_df, weights)
    trend_data = build_trend_data(signals_df, weights)  # ← add this line
```

Then add `trend_data_json` to the `template.render()` call:

```python
    html = template.render(
        btc_price=btc_price,
        updated_date=current_score["date"],
        updated_at=updated_at,
        composite_score=composite,
        verdict=verdict,
        score_color=get_score_color(verdict),
        distance_text=distance_text,
        signals=signals,
        chart_data_json=json.dumps(chart_data),
        trend_data_json=json.dumps(trend_data),   # ← add this line
        methodology=methodology,
    )
```

- [ ] **Step 2: Run the build and confirm `trend_data_json` is embedded**

```
python scripts/build_dashboard.py
```

Expected output: `Dashboard written to docs/index.html (XX,XXX bytes)`

Then verify:
```
python -c "
content = open('docs/index.html', encoding='utf-8').read()
assert 'trend_data_json' not in content, 'variable name leaked — should be the value'
assert '\"day\"' in content and '\"week\"' in content and '\"month\"' in content
assert '\"spark\"' in content and '\"arrows\"' in content
print('OK — trend data embedded correctly')
"
```

Expected: `OK — trend data embedded correctly`

- [ ] **Step 3: Commit**

```
git add scripts/build_dashboard.py docs/index.html
git commit -m "feat: embed trend_data_json in dashboard HTML via build_dashboard"
```

---

## Task 3: Template — CSS + HTML structure (toggle, delta, sparkline, arrow column)

**Files:**
- Modify: `templates/dashboard.html.j2`

This task adds all the static HTML structure and CSS. The JS (Task 4) activates it. After this task, the toggle buttons render but don't work yet; the delta and sparkline are empty; the arrow column cells are empty.

- [ ] **Step 1: Add CSS for trend elements**

In `templates/dashboard.html.j2`, insert the following CSS block right after the `.distance strong { font-weight: 600; }` line (currently inside the `<style>` block):

```css
    /* ── trend toggle ── */
    .trend-toggle { display: flex; justify-content: center; gap: 6px; margin-bottom: 1rem; }
    .trend-toggle button { background: #1e1e1e; color: #555; border: none; border-radius: 20px; padding: 5px 18px; font-size: 12px; font-weight: 700; cursor: pointer; transition: background .15s, color .15s; }
    .trend-toggle button.active { background: #fff; color: #000; }

    /* ── trend delta + sparkline ── */
    .trend-delta { margin-top: 0.6rem; font-size: 0.95rem; font-weight: 600; min-height: 1.2em; }
    .sparkline-wrap { margin-top: 0.9rem; }
    .sparkline { display: flex; align-items: flex-end; justify-content: center; gap: 4px; height: 44px; padding-top: 8px; }
    .spark-bar { border-radius: 2px 2px 0 0; cursor: pointer; position: relative; flex-shrink: 0; }
    .spark-bar:hover .spark-tip, .spark-bar.tip-open .spark-tip { display: block; }
    .spark-tip { display: none; position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%); background: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 5px; padding: 3px 8px; white-space: nowrap; font-size: 0.72rem; color: #e0e0e0; pointer-events: none; z-index: 10; }
    .spark-tip::after { content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%); border: 4px solid transparent; border-top-color: #3a3a3a; }
    .spark-lbl { font-size: 0.7rem; color: #444; margin-top: 4px; }

    /* ── signal trend arrow column ── */
    .trend-arrow { font-size: 1.05rem; font-weight: 700; }
    td.trend-col { width: 28px; text-align: center; padding: 0.85rem 0.25rem; }
    th.trend-col { width: 28px; text-align: center; color: #333; font-size: 0.65rem; padding: 0.6rem 0.25rem; }
```

- [ ] **Step 2: Add the toggle between the header and the score card**

In the template body, find the line `<div class="score-card">` and insert the toggle **before** it:

```html
  <div class="trend-toggle">
    <button id="tw-day"   onclick="setTrendWindow('day')">Day</button>
    <button id="tw-week"  onclick="setTrendWindow('week')">Week</button>
    <button id="tw-month" onclick="setTrendWindow('month')">Month</button>
  </div>

  <div class="score-card">
```

- [ ] **Step 3: Add the delta line and sparkline inside the score card**

Inside `.score-card`, find `<div class="verdict">{{ verdict }}</div>` and add the delta line immediately after it:

```html
    <div class="verdict">{{ verdict }}</div>
    <div id="trend-delta" class="trend-delta"></div>
```

Then find the closing `</div>` of `.zone-strip-wrap` and add the sparkline after it (still inside `.score-card`):

```html
    </div><!-- end .zone-strip-wrap -->

    <div class="sparkline-wrap">
      <div id="sparkline" class="sparkline"></div>
      <div id="spark-lbl" class="spark-lbl"></div>
    </div>
  </div><!-- end .score-card -->
```

- [ ] **Step 4: Add the arrow column to the signal table**

In `<thead>`, add the trend column header after `<th>Reading</th>`:

```html
        <th>Signal</th>
        <th>Reading</th>
        <th class="trend-col">▲▼</th>
        <th><span style="color:#ff525255">← Avoid</span> ...
```

In `<tbody>`, inside the `{% for name, sig in signals.items() %}` loop, add the arrow `<td>` after the reading cell:

```html
      <tr>
        <td>{{ sig.display_name }}</td>
        <td>{{ sig.reading_formatted }}</td>
        <td class="trend-col"><span class="trend-arrow" data-sig="{{ name }}"></span></td>
        <td>
          {% if sig.bar.has_data %}
          ...
```

- [ ] **Step 5: Build and do a smoke-check**

```
python scripts/build_dashboard.py
```

Open `docs/index.html` in a browser. You should see:
- Three pill buttons (Day / Week / Month) above the score card — unstyled/inactive
- An empty line where the delta will appear
- An empty sparkline area below the zone strip
- An extra narrow `▲▼` column in the signal table with empty cells

Nothing interactive yet — that's expected. The JS is in Task 4.

- [ ] **Step 6: Commit**

```
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: add trend toggle, delta, sparkline, and arrow column HTML/CSS"
```

---

## Task 4: JavaScript toggle logic + final verification

**Files:**
- Modify: `templates/dashboard.html.j2` (JS block only)

- [ ] **Step 1: Add the trend JS block to the template**

In `templates/dashboard.html.j2`, find the closing `</script>` tag of the existing Chart.js block (at the very bottom, just before `</body>`). Add a new `<script>` block **after** it:

```html
  <script>
    (function () {
      const TREND = {{ trend_data_json }};

      function zoneColor(s) {
        return s >= 80 ? '#00e676' : s >= 72 ? '#00c853' : s >= 50 ? '#ff9800' : s >= 25 ? '#ffd740' : '#ff5252';
      }

      function setTrendWindow(w) {
        const d = TREND[w];

        // Delta line
        const sign   = d.delta >= 0 ? '+' : '';
        const arr    = d.delta > 0.5 ? '↑' : d.delta < -0.5 ? '↓' : '→';
        const col    = d.delta > 0.5 ? '#00c853' : d.delta < -0.5 ? '#ff5252' : '#888';
        const lbl    = { day: 'yesterday', week: 'last week', month: 'last month' }[w];
        const deltaEl = document.getElementById('trend-delta');
        deltaEl.textContent = arr + ' ' + sign + d.delta.toFixed(1) + ' pts vs ' + lbl;
        deltaEl.style.color = col;

        // Sparkline
        const scores = d.spark.map(function(p) { return p.score; });
        const mx = Math.max.apply(null, scores);
        const mn = Math.min.apply(null, scores) - 3;
        document.getElementById('sparkline').innerHTML = d.spark.map(function(p, i) {
          var h    = Math.round(((p.score - mn) / (mx - mn)) * 30) + 4;
          var last = i === d.spark.length - 1;
          var opacity = (0.35 + 0.65 * (i / (d.spark.length - 1))).toFixed(2);
          var bg   = last ? zoneColor(p.score) : '#2a2a2a';
          var w_px = last ? 10 : 8;
          return '<div class="spark-bar" style="width:' + w_px + 'px;height:' + h + 'px;background:' + bg + ';opacity:' + opacity + ';">'
               + '<div class="spark-tip">' + p.label + '<br><strong style="color:' + zoneColor(p.score) + '">' + p.score + ' — ' + p.verdict + '</strong></div>'
               + '</div>';
        }).join('');
        var sparkLbls = { day: 'last 7 days', week: 'last 7 weeks', month: 'last 7 months' };
        document.getElementById('spark-lbl').textContent = sparkLbls[w];

        // Signal arrows
        var arrowChar  = { '1': '↑', '0': '→', '-1': '↓' };
        var arrowColor = { '1': '#00c853', '0': '#ffd740', '-1': '#ff5252' };
        document.querySelectorAll('.trend-arrow[data-sig]').forEach(function(el) {
          var sig = el.getAttribute('data-sig');
          var v   = String(d.arrows[sig]);
          el.textContent  = arrowChar[v]  || '→';
          el.style.color  = arrowColor[v] || '#ffd740';
        });

        // Toggle button active state
        ['day', 'week', 'month'].forEach(function(k) {
          document.getElementById('tw-' + k).classList.toggle('active', k === w);
        });

        try { localStorage.setItem('kairos-trend-window', w); } catch(e) {}
      }

      // Restore last-used window (default: day)
      var saved = '';
      try { saved = localStorage.getItem('kairos-trend-window') || ''; } catch(e) {}
      var init = ['day', 'week', 'month'].indexOf(saved) !== -1 ? saved : 'day';
      setTrendWindow(init);

      window.setTrendWindow = setTrendWindow;
    })();
  </script>
```

- [ ] **Step 2: Rebuild**

```
python scripts/build_dashboard.py
```

Expected: `Dashboard written to docs/index.html (XX,XXX bytes)`

- [ ] **Step 3: Verify interactivity in browser**

Serve the file locally:

```
python -m http.server 8080 --directory docs
```

Open `http://localhost:8080/index.html`. Verify:

1. "Day" button is active (white pill) on load
2. Delta line shows e.g. `↑ +2.1 pts vs yesterday` in green/red/grey
3. Sparkline shows 7 bars; rightmost bar is zone-colored; others are dark grey
4. Hovering a sparkline bar shows a tooltip with date label + score + verdict
5. Clicking "Week" updates delta label to "vs last week", sparkline changes, signal arrows update
6. Clicking "Month" does the same
7. Refreshing the page restores the last-used window (localStorage)
8. All 6 signal rows have a direction arrow (↑ → ↓) in the narrow column

Stop the server with Ctrl+C.

- [ ] **Step 4: Run full test suite**

```
python -m pytest -q
```

Expected: 39 passed.

- [ ] **Step 5: Commit and push**

```
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: add trend toggle JS — connects Day/Week/Month to delta, sparkline, arrows"
git push
```

After push, wait ~2 minutes for GitHub Pages to deploy, then verify at `https://meyogui.github.io/fbtc-timing/`.
