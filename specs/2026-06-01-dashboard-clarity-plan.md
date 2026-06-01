# Dashboard Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ambiguous score card verdict and signal status dots with a zone strip (composite) and range bars (signals) so the invest/wait decision is instant and legible.

**Architecture:** `score.py` adds a `SIGNAL_META` constant and writes it into `current_score.json`. `build_dashboard.py` reads that metadata and pre-computes per-signal bar geometry before passing it to the Jinja2 template. The template renders the zone strip and signal bars using those pre-computed values — no logic in the template.

**Tech Stack:** Python 3.11, Jinja2, vanilla HTML/CSS (no new dependencies)

**Visual reference:** `specs/dashboard-clarity-reference.png` — implementation must match this screenshot.

---

## File Map

| File | Change |
|---|---|
| `scripts/score.py` | Add `SIGNAL_META` dict; update `get_verdict()` for 5 zones; write `signal_meta` into `current_score.json` |
| `scripts/build_dashboard.py` | Add `compute_signal_bar()`; update `get_score_color()`; remove `STATUS_LABELS`; pass bar data + distance text to template |
| `templates/dashboard.html.j2` | Add zone strip CSS + HTML in score card; replace status column with range bar HTML; update table header |
| `tests/test_score.py` | Update verdict boundary tests for 5 zones |
| `tests/test_build_dashboard.py` | New file — tests for `compute_signal_bar()` |

---

## Task 1: Update `get_verdict()` for 5 zones

**Files:**
- Modify: `scripts/score.py`
- Modify: `tests/test_score.py`

- [ ] **Step 1: Update the verdict tests**

Replace all verdict tests in `tests/test_score.py` with:

```python
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from score import compute_score, get_verdict, SIGNAL_DISPLAY

EQUAL_WEIGHTS = {
    "signals": {name: {"weight": 1/6} for name in SIGNAL_DISPLAY}
}


def test_get_verdict_avoid():
    assert get_verdict(0) == "AVOID"
    assert get_verdict(24.9) == "AVOID"


def test_get_verdict_wait():
    assert get_verdict(25) == "WAIT"
    assert get_verdict(49.9) == "WAIT"


def test_get_verdict_close():
    assert get_verdict(50) == "CLOSE"
    assert get_verdict(71.9) == "CLOSE"


def test_get_verdict_invest():
    assert get_verdict(72) == "INVEST"
    assert get_verdict(79.9) == "INVEST"


def test_get_verdict_strong_buy():
    assert get_verdict(80) == "STRONG BUY"
    assert get_verdict(100) == "STRONG BUY"


def test_compute_score_all_buy():
    signals = {name: {"score": 100} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(100.0, abs=0.1)


def test_compute_score_all_avoid():
    signals = {name: {"score": 0} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(0.0, abs=0.1)


def test_compute_score_mixed():
    signals = {name: {"score": 100 if i % 2 == 0 else 0} for i, name in enumerate(SIGNAL_DISPLAY)}
    score = compute_score(signals, EQUAL_WEIGHTS)
    assert 40 < score < 60
```

- [ ] **Step 2: Run tests — expect failures on verdict tests**

```
pytest tests/test_score.py -v
```

Expected: `test_get_verdict_*` tests fail (old thresholds), score tests pass.

- [ ] **Step 3: Update `get_verdict()` in `scripts/score.py`**

Replace the existing `get_verdict` function:

```python
def get_verdict(score: float) -> str:
    if score >= 80:
        return "STRONG BUY"
    if score >= 72:
        return "INVEST"
    if score >= 50:
        return "CLOSE"
    if score >= 25:
        return "WAIT"
    return "AVOID"
```

- [ ] **Step 4: Run tests — all pass**

```
pytest tests/test_score.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```
git add scripts/score.py tests/test_score.py
git commit -m "feat: update get_verdict for 5 zones (AVOID/WAIT/CLOSE/INVEST/STRONG BUY)"
```

---

## Task 2: Add SIGNAL_META and write to current_score.json

**Files:**
- Modify: `scripts/score.py`

- [ ] **Step 1: Add `SIGNAL_META` constant to `scripts/score.py`**

Add after the `SIGNAL_DISPLAY` dict:

```python
SIGNAL_META = {
    "mvrv_zscore": {
        "range_lo": -3.0, "range_hi": 4.0,
        "invest_thresh": -0.5, "avoid_thresh": 1.5,
        "fmt": "{:.1f}",
    },
    "ma_200w": {
        "range_lo": 0.5, "range_hi": 3.0,
        "invest_thresh": 1.0, "avoid_thresh": 1.2,
        "fmt": "{:.1f}×",
    },
    "monthly_rsi": {
        "range_lo": 0.0, "range_hi": 100.0,
        "invest_thresh": 40.0, "avoid_thresh": 70.0,
        "fmt": "{:.0f}",
    },
    "pi_cycle": {
        "range_lo": 0.0, "range_hi": 1.5,
        "invest_thresh": 0.9, "avoid_thresh": 1.0,
        "fmt": "{:.1f}",
    },
    "puell": {
        "range_lo": 0.0, "range_hi": 4.0,
        "invest_thresh": 0.5, "avoid_thresh": 1.5,
        "fmt": "{:.1f}",
    },
    "fear_greed": {
        "range_lo": 0.0, "range_hi": 100.0,
        "invest_thresh": 25.0, "avoid_thresh": 50.0,
        "fmt": "{:.0f}",
    },
}
```

- [ ] **Step 2: Write `signal_meta` into `current_score.json` in `main()`**

In `score.py`'s `main()`, update the `output` dict to include `signal_meta`:

```python
    output = {
        "date": current["date"],
        "composite_score": composite,
        "verdict": verdict,
        "signals": {
            name: {
                "display_name": SIGNAL_DISPLAY[name],
                "raw": _sanitize_float(data["raw"]),
                "score": data["score"],
                "status": "buy" if data["score"] == 100 else ("avoid" if data["score"] == 0 else "neutral"),
            }
            for name, data in current["signals"].items()
        },
        "weights": {name: weights["signals"][name]["weight"] for name in weights["signals"]},
        "signal_meta": SIGNAL_META,
    }
```

- [ ] **Step 3: Verify the JSON output**

```
python scripts/score.py
```

Expected output (last line): `Score: 57.6/100 — CLOSE`

Then check the file contains `signal_meta`:

```
python -c "import json; d=json.load(open('data/current_score.json')); print(list(d['signal_meta'].keys()))"
```

Expected: `['mvrv_zscore', 'ma_200w', 'monthly_rsi', 'pi_cycle', 'puell', 'fear_greed']`

- [ ] **Step 4: Commit**

```
git add scripts/score.py
git commit -m "feat: add SIGNAL_META and write signal_meta block to current_score.json"
```

---

## Task 3: Update `build_dashboard.py`

**Files:**
- Modify: `scripts/build_dashboard.py`
- Create: `tests/test_build_dashboard.py`

- [ ] **Step 1: Write failing tests for `compute_signal_bar()`**

Create `tests/test_build_dashboard.py`:

```python
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_dashboard import compute_signal_bar

MVRV_META = {
    "range_lo": -3.0, "range_hi": 4.0,
    "invest_thresh": -0.5, "avoid_thresh": 1.5,
    "fmt": "{:.1f}",
}

FEAR_META = {
    "range_lo": 0.0, "range_hi": 100.0,
    "invest_thresh": 25.0, "avoid_thresh": 50.0,
    "fmt": "{:.0f}",
}


def test_no_data_returns_has_data_false():
    result = compute_signal_bar("mvrv_zscore", None, 50, MVRV_META)
    assert result["has_data"] is False


def test_invest_zone_status():
    # raw=-1.0 is below invest_thresh=-0.5, score=100
    result = compute_signal_bar("mvrv_zscore", -1.0, 100, MVRV_META)
    assert result["has_data"] is True
    assert result["status_class"] == "st-invest"
    assert result["status_text"].startswith("INVEST")


def test_avoid_zone_status():
    # raw=2.0 is above avoid_thresh=1.5, score=0
    result = compute_signal_bar("mvrv_zscore", 2.0, 0, MVRV_META)
    assert result["status_class"] == "st-avoid"
    assert result["status_text"] == "AVOID"


def test_wait_zone_closer_to_invest():
    # raw=-0.25, invest_thresh=-0.5, avoid_thresh=1.5
    # dist_invest=0.25, dist_avoid=1.75 → closer to invest
    result = compute_signal_bar("mvrv_zscore", -0.25, 50, MVRV_META)
    assert result["status_class"] == "st-wait"
    assert "from invest" in result["status_text"]


def test_wait_zone_closer_to_avoid():
    # raw=1.4, dist_avoid=0.1, dist_invest=1.9 → closer to avoid
    result = compute_signal_bar("mvrv_zscore", 1.4, 50, MVRV_META)
    assert "from avoid" in result["status_text"]
    assert "⚠️" in result["status_text"]


def test_cursor_clamped_at_bounds():
    # raw beyond range_hi should clamp to 0%
    result = compute_signal_bar("mvrv_zscore", 10.0, 0, MVRV_META)
    assert result["cursor_pct"] == 0.0
    # raw beyond range_lo should clamp to 100%
    result = compute_signal_bar("mvrv_zscore", -10.0, 100, MVRV_META)
    assert result["cursor_pct"] == 100.0


def test_zone_widths_sum_to_100():
    result = compute_signal_bar("mvrv_zscore", -0.25, 50, MVRV_META)
    total = result["avoid_pct"] + result["wait_pct"] + result["invest_pct"]
    assert abs(total - 100.0) < 0.2  # floating point tolerance


def test_thresh_positions_ordered():
    result = compute_signal_bar("mvrv_zscore", -0.25, 50, MVRV_META)
    # avoid threshold is to the LEFT of invest threshold on the bar
    assert result["thresh_avoid_pct"] < result["thresh_invest_pct"]


def test_fear_greed_invest_labels():
    # F&G fmt is "{:.0f}", range_hi=100, range_lo=0
    result = compute_signal_bar("fear_greed", 23.0, 100, FEAR_META)
    assert result["edge_left"] == "100"
    assert result["edge_right"] == "0"
    assert result["thresh_avoid_lbl"] == "50"
    assert result["thresh_invest_lbl"] == "25"
```

- [ ] **Step 2: Run tests — expect ImportError or AttributeError**

```
pytest tests/test_build_dashboard.py -v
```

Expected: FAIL — `compute_signal_bar` not defined yet.

- [ ] **Step 3: Add `compute_signal_bar()` and update `get_score_color()` in `build_dashboard.py`**

Replace the existing `get_score_color` function and add `compute_signal_bar` after it:

```python
def get_score_color(verdict: str) -> str:
    return {
        "STRONG BUY": "#00e676",
        "INVEST":     "#00c853",
        "CLOSE":      "#ff9800",
        "WAIT":       "#ffd740",
        "AVOID":      "#ff5252",
    }.get(verdict, "#ffd740")


def compute_signal_bar(name: str, raw, score: int, meta: dict) -> dict:
    if raw is None:
        return {"has_data": False}

    span = meta["range_hi"] - meta["range_lo"]
    avoid_pct  = round((meta["range_hi"] - meta["avoid_thresh"])  / span * 100, 1)
    wait_pct   = round((meta["avoid_thresh"] - meta["invest_thresh"]) / span * 100, 1)
    invest_pct = round(100.0 - avoid_pct - wait_pct, 1)

    cursor_pct = (meta["range_hi"] - float(raw)) / span * 100
    cursor_pct = round(max(0.0, min(100.0, cursor_pct)), 1)

    thresh_avoid_pct  = avoid_pct
    thresh_invest_pct = round(avoid_pct + wait_pct, 1)

    dist_invest = abs(float(raw) - meta["invest_thresh"])
    dist_avoid  = abs(float(raw) - meta["avoid_thresh"])

    if score == 100:
        status_class = "st-invest"
        status_text  = "INVEST"
    elif score == 0:
        status_class = "st-avoid"
        status_text  = "AVOID"
    elif dist_invest <= dist_avoid:
        status_class = "st-wait"
        status_text  = f"WAIT · {dist_invest:.2g} from invest"
    else:
        status_class = "st-wait"
        status_text  = f"WAIT · {dist_avoid:.2g} from avoid ⚠️"

    fmt = meta["fmt"]
    return {
        "has_data":          True,
        "avoid_pct":         avoid_pct,
        "wait_pct":          wait_pct,
        "invest_pct":        invest_pct,
        "cursor_pct":        cursor_pct,
        "thresh_avoid_pct":  thresh_avoid_pct,
        "thresh_invest_pct": thresh_invest_pct,
        "edge_left":         fmt.format(meta["range_hi"]),
        "edge_right":        fmt.format(meta["range_lo"]),
        "thresh_avoid_lbl":  fmt.format(meta["avoid_thresh"]),
        "thresh_invest_lbl": fmt.format(meta["invest_thresh"]),
        "status_class":      status_class,
        "status_text":       status_text,
    }
```

Also remove the `STATUS_LABELS` dict (no longer used).

- [ ] **Step 4: Run tests — all pass**

```
pytest tests/test_build_dashboard.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Update `main()` in `build_dashboard.py` to pass bar data to template**

Replace the `signals` dict construction and `template.render()` call in `main()`:

```python
    signal_meta = current_score["signal_meta"]

    signals = {}
    for name, data in current_score["signals"].items():
        signals[name] = {
            "display_name":     data["display_name"],
            "reading_formatted": format_reading(name, data["raw"]),
            "bar": compute_signal_bar(
                name,
                data["raw"],
                data["score"],
                signal_meta[name],
            ),
        }

    composite = current_score["composite_score"]
    verdict   = current_score["verdict"]

    if composite >= 80:
        distance_text = "You are in the Strong Buy zone"
    elif composite >= 72:
        distance_text = "You are in the Invest Zone"
    else:
        distance_text = f"{72 - composite:.1f} pts from Invest zone"

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("dashboard.html.j2")
    html = template.render(
        btc_price=btc_price,
        updated_date=current_score["date"],
        composite_score=composite,
        verdict=verdict,
        score_color=get_score_color(verdict),
        distance_text=distance_text,
        signals=signals,
        chart_data_json=json.dumps(chart_data),
        methodology=methodology,
    )
```

- [ ] **Step 6: Run full test suite**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```
git add scripts/build_dashboard.py tests/test_build_dashboard.py
git commit -m "feat: add compute_signal_bar and bar data to dashboard context"
```

---

## Task 4: Update template — score card zone strip

**Files:**
- Modify: `templates/dashboard.html.j2`

- [ ] **Step 1: Add zone strip CSS to the `<style>` block**

Add after the `.verdict { ... }` rule:

```css
    /* ── zone strip (score card) ── */
    .zone-strip-wrap { max-width: 480px; margin: 1.5rem auto 0; }
    .zone-strip { display: flex; height: 34px; border-radius: 7px; overflow: hidden; position: relative; }
    .zone { display: flex; align-items: center; justify-content: center; font-size: 0.6rem; font-weight: 700; letter-spacing: 0.04em; }
    .z-avoid  { flex: 25; background: #ff523218; color: #ff5252; }
    .z-wait   { flex: 25; background: #ffd74018; color: #ffd740; }
    .z-close  { flex: 22; background: #ff980022; color: #ff9800; }
    .z-invest { flex: 8;  background: #00c85328; color: #00c853; }
    .z-strong { flex: 20; background: #00c85448; color: #00e676; font-size: 0.55rem; }
    .z-cursor {
      position: absolute; top: 0; width: 2px; height: 100%;
      background: #fff; border-radius: 2px;
      box-shadow: 0 0 10px rgba(255,255,255,0.9);
    }
    .strip-labels { position: relative; height: 18px; margin-top: 5px; }
    .strip-label { position: absolute; font-size: 0.68rem; color: #3a3a3a; transform: translateX(-50%); white-space: nowrap; }
    .strip-label.edge-l { transform: translateX(0); }
    .strip-label.edge-r { transform: translateX(-100%); }
    .distance { margin-top: 0.85rem; font-size: 0.9rem; color: #888; }
    .distance strong { font-weight: 600; }
```

- [ ] **Step 2: Replace the score card verdict HTML with verdict + zone strip**

Replace:
```html
    <div class="verdict">{{ verdict }}</div>
  </div>
```

With:
```html
    <div class="verdict">{{ verdict }}</div>

    <div class="zone-strip-wrap">
      <div class="zone-strip">
        <div class="zone z-avoid">AVOID</div>
        <div class="zone z-wait">WAIT</div>
        <div class="zone z-close">CLOSE</div>
        <div class="zone z-invest">INVEST</div>
        <div class="zone z-strong">STRONG BUY</div>
        <div class="z-cursor" style="left: {{ composite_score }}%"></div>
      </div>
      <div class="strip-labels">
        <span class="strip-label edge-l" style="color:#ff5252">0</span>
        <span class="strip-label" style="left:25%; color:#ffd740">25</span>
        <span class="strip-label" style="left:50%; color:#ff9800">50</span>
        <span class="strip-label" style="left:72%; color:#00c853">72</span>
        <span class="strip-label" style="left:80%; color:#00e676">80</span>
        <span class="strip-label edge-r" style="left:100%; color:#555">100</span>
      </div>
      <div class="distance"><strong style="color: {{ score_color }}">{{ distance_text }}</strong></div>
    </div>
  </div>
```

- [ ] **Step 3: Build the dashboard and check visually**

```
python scripts/build_dashboard.py
```

Open `docs/index.html` in a browser. The score card should show the number, CLOSE verdict, and zone strip with white cursor at 57.6%.

- [ ] **Step 4: Commit**

```
git add templates/dashboard.html.j2
git commit -m "feat: add zone strip to score card"
```

---

## Task 5: Update template — signal table range bars

**Files:**
- Modify: `templates/dashboard.html.j2`

- [ ] **Step 1: Add signal bar CSS to the `<style>` block**

Add after the zone strip styles (and remove the `.dot` rules):

```css
    /* ── signal range bars ── */
    .sig-bar-wrap { display: flex; flex-direction: column; gap: 4px; }
    .sig-status { display: inline-block; align-self: flex-start; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.04em; padding: 1px 7px; border-radius: 3px; }
    .st-invest { background: #00c85318; color: #00c853; }
    .st-wait   { background: #ffd74018; color: #ffd740; }
    .st-avoid  { background: #ff525218; color: #ff5252; }
    .bar-outer { position: relative; height: 26px; }
    .bar-track { position: absolute; top: 50%; transform: translateY(-50%); left: 0; right: 0; height: 9px; border-radius: 5px; display: flex; overflow: hidden; }
    .seg-avoid  { background: #ff525228; }
    .seg-wait   { background: #ffd74022; }
    .seg-invest { background: #00c85328; }
    .thresh-line { position: absolute; top: 50%; transform: translateY(-50%); width: 1px; height: 13px; background: #484848; border-radius: 1px; }
    .sig-cursor { position: absolute; top: 0; bottom: 0; width: 2px; background: #fff; border-radius: 2px; box-shadow: 0 0 7px rgba(255,255,255,0.85); transform: translateX(-50%); }
    .sig-cursor::before { content: ''; position: absolute; top: -2px; left: 50%; transform: translateX(-50%) rotate(45deg); width: 5px; height: 5px; background: #fff; box-shadow: 0 0 4px rgba(255,255,255,0.9); }
    .bar-labels { position: relative; height: 14px; }
    .bar-label { position: absolute; font-size: 0.7rem; color: #484848; transform: translateX(-50%); white-space: nowrap; }
    .bar-label.edge-l { transform: translateX(0); color: #ff525277; font-size: 0.65rem; }
    .bar-label.edge-r { transform: translateX(-100%); color: #00c85377; font-size: 0.65rem; }
```

- [ ] **Step 2: Update the signal table header**

Replace:
```html
      <tr><th>Signal</th><th>Reading</th><th>Status</th></tr>
```

With:
```html
      <tr>
        <th>Signal</th>
        <th>Reading</th>
        <th><span style="color:#ff525255">← Avoid</span> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <span style="color:#00c85355">Invest →</span></th>
      </tr>
```

- [ ] **Step 3: Replace the signal table body rows**

Replace the `{% for name, sig in signals.items() %}` block:

```html
      {% for name, sig in signals.items() %}
      <tr>
        <td>{{ sig.display_name }}</td>
        <td>{{ sig.reading_formatted }}</td>
        <td>
          {% if sig.bar.has_data %}
          <div class="sig-bar-wrap">
            <span class="sig-status {{ sig.bar.status_class }}">{{ sig.bar.status_text }}</span>
            <div class="bar-outer">
              <div class="bar-track">
                <div class="seg-avoid" style="width:{{ sig.bar.avoid_pct }}%"></div>
                <div class="seg-wait"  style="width:{{ sig.bar.wait_pct }}%"></div>
                <div class="seg-invest"style="width:{{ sig.bar.invest_pct }}%"></div>
              </div>
              <div class="thresh-line" style="left:{{ sig.bar.thresh_avoid_pct }}%"></div>
              <div class="thresh-line" style="left:{{ sig.bar.thresh_invest_pct }}%"></div>
              <div class="sig-cursor"  style="left:{{ sig.bar.cursor_pct }}%"></div>
            </div>
            <div class="bar-labels">
              <span class="bar-label edge-l">{{ sig.bar.edge_left }}</span>
              <span class="bar-label" style="left:{{ sig.bar.thresh_avoid_pct }}%; color:#555">{{ sig.bar.thresh_avoid_lbl }}</span>
              <span class="bar-label" style="left:{{ sig.bar.thresh_invest_pct }}%; color:#555">{{ sig.bar.thresh_invest_lbl }}</span>
              <span class="bar-label edge-r" style="left:100%">{{ sig.bar.edge_right }}</span>
            </div>
          </div>
          {% else %}
          <span style="color:#444; font-size:0.8rem">No data</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
```

- [ ] **Step 4: Build and verify visually**

```
python scripts/build_dashboard.py
```

Open `docs/index.html` in a browser. Compare against `specs/dashboard-clarity-reference.png`:
- Score card has zone strip with cursor at ~57.6%
- Each signal row has a coloured range bar with white cursor, grey threshold lines, and labels
- 200-Week MA cursor should be nearly touching the avoid threshold on the left
- Pi Cycle and Fear & Greed cursors deep in the green zone on the right
- Puell Multiple shows "No data"

- [ ] **Step 5: Run all tests**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```
git add templates/dashboard.html.j2
git commit -m "feat: replace signal status dots with range bars"
```

---

## Task 6: End-to-End Verification and Push

**Files:** none (verification only)

- [ ] **Step 1: Run full pipeline**

```
python scripts/fetch_data.py
python scripts/compute_signals.py
python scripts/score.py
python scripts/build_dashboard.py
```

Expected: no errors, `docs/index.html` updated.

- [ ] **Step 2: Check score verdict label**

```
python -c "import json; d=json.load(open('data/current_score.json')); print(d['verdict'], d['composite_score'])"
```

Expected: `CLOSE 57.6` (or current value — verdict must be one of AVOID/WAIT/CLOSE/INVEST/STRONG BUY).

- [ ] **Step 3: Check signal_meta present in JSON**

```
python -c "import json; d=json.load(open('data/current_score.json')); print(list(d['signal_meta'].keys()))"
```

Expected: `['mvrv_zscore', 'ma_200w', 'monthly_rsi', 'pi_cycle', 'puell', 'fear_greed']`

- [ ] **Step 4: Run full test suite one final time**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: Push**

```
git push origin main
```

- [ ] **Step 6: Verify live dashboard**

Navigate to `https://meyogui.github.io/fbtc-timing` after the GitHub Actions daily workflow runs (or trigger it manually). Compare with `specs/dashboard-clarity-reference.png`.
