# Signal Freshness Captions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each dashboard signal card its natural cadence (Daily/Monthly) and the date its current reading is actually from, without changing any scoring math.

**Architecture:** Additive only. `SignalSpec` gains a `cadence` field; `compute_signals.py` derives an `as_of` date (last value-change) per signal; `score.py` passes `cadence` + `as_of` into `{id}_score.json`; `build_dashboard.py` formats a `freshness` caption string (computing `next_refresh` for monthly signals); the Jinja template renders one muted line per card. The composite/spectrum pipeline is untouched and guarded by a regression test.

**Tech Stack:** Python 3.11, pandas, pytest, Jinja2, Tailwind (CDN) template.

**Spec:** `docs/superpowers/specs/2026-06-21-signal-freshness-design.md`

---

## File Structure

- Modify `assets/base.py` — add `cadence: str = "daily"` to `SignalSpec`.
- Modify `assets/bitcoin.py` — `cadence="monthly"` on the `monthly_rsi` spec.
- Modify `assets/eth.py` — `cadence="monthly"` on the `monthly_rsi` spec.
- Modify `scripts/compute_signals.py` — add `last_change_date()`; write `as_of` into `current_signals.json`.
- Modify `scripts/score.py` — add `build_signal_entry()`; emit `cadence` + `as_of`.
- Modify `scripts/build_dashboard.py` — add `next_refresh_date()`, `_fmt_md()`, `format_freshness()`; attach `freshness` to each signal blob.
- Modify `templates/dashboard.html.j2` — render the caption line in `metricCardHTML`.
- Create `tests/test_freshness.py` — all new unit tests.

Tests import from `scripts` and `assets` exactly like `tests/test_compute_signals.py` and `tests/test_score.py` (they prepend `scripts/` to `sys.path`).

---

### Task 1: Add `cadence` to SignalSpec and mark Monthly RSI

**Files:**
- Modify: `assets/base.py:8-19` (the `SignalSpec` dataclass)
- Modify: `assets/bitcoin.py:170-172` (the `monthly_rsi` SignalSpec)
- Modify: `assets/eth.py:157-159` (the `monthly_rsi` SignalSpec)
- Test: `tests/test_freshness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_freshness.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_monthly_rsi_cadence_is_monthly_others_daily():
    from assets.bitcoin import CONFIG as BTC
    from assets.eth import CONFIG as ETH
    for cfg in (BTC, ETH):
        rsi = next(s for s in cfg.signals if s.key == "monthly_rsi")
        assert rsi.cadence == "monthly"
        others = [s for s in cfg.signals if s.key != "monthly_rsi"]
        assert all(s.cadence == "daily" for s in others), cfg.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_freshness.py::test_monthly_rsi_cadence_is_monthly_others_daily -v`
Expected: FAIL — `TypeError: SignalSpec.__init__() got an unexpected keyword argument 'cadence'` is not raised yet because the field doesn't exist; the failure will be `AttributeError: 'SignalSpec' object has no attribute 'cadence'`.

- [ ] **Step 3: Add the field**

In `assets/base.py`, add the field to `SignalSpec` (after `fmt`, with a default so existing call sites stay valid):

```python
@dataclass
class SignalSpec:
    """Binds a shared signal compute-function to one asset's thresholds + display meta."""
    key: str
    display_name: str
    compute: Callable[[pd.DataFrame], pd.Series]
    invest_thresh: float
    avoid_thresh: float
    sell_thresh: float        # raw value ABOVE which signal says "sell" (score = 100)
    range_lo: float
    range_hi: float
    fmt: str
    cadence: str = "daily"    # natural update rate: "daily" or "monthly"
```

- [ ] **Step 4: Mark Monthly RSI in both assets**

In `assets/bitcoin.py`, the `monthly_rsi` spec — append `cadence="monthly"`:

```python
        SignalSpec("monthly_rsi", "Monthly RSI", compute_monthly_rsi,
                   invest_thresh=40.0, avoid_thresh=70.0, sell_thresh=78.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}", cadence="monthly"),
```

In `assets/eth.py`, the `monthly_rsi` spec — append `cadence="monthly"` the same way (keep its existing threshold/range/fmt values; only add the kwarg at the end of the call).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_freshness.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add assets/base.py assets/bitcoin.py assets/eth.py tests/test_freshness.py
git commit -m "feat: add cadence field to SignalSpec; mark Monthly RSI monthly"
```

---

### Task 2: `last_change_date()` and `as_of` in current_signals.json

**Files:**
- Modify: `scripts/compute_signals.py` (add helper near top; write `as_of` in `_process_asset`)
- Test: `tests/test_freshness.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_freshness.py`:

```python
import numpy as np
import pandas as pd
from compute_signals import last_change_date


def _dates(n, start="2026-01-01"):
    return pd.Series(pd.date_range(start, periods=n))


def test_last_change_daily_moving_returns_last_date():
    d = _dates(5)
    raw = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4])
    assert last_change_date(d, raw) == d.iloc[-1].date()


def test_last_change_monthly_ffill_returns_month_boundary():
    # value steps once at index 31 (a new month), then holds flat to the end
    d = _dates(60)
    raw = pd.Series([10.0] * 31 + [12.0] * 29)
    assert last_change_date(d, raw) == d.iloc[31].date()


def test_last_change_trailing_nan_returns_last_real_change():
    # daily-moving then 2 lagging NaN days at the end
    d = _dates(5)
    raw = pd.Series([1.0, 1.1, 1.2, np.nan, np.nan])
    assert last_change_date(d, raw) == d.iloc[2].date()


def test_last_change_all_nan_returns_none():
    d = _dates(3)
    raw = pd.Series([np.nan, np.nan, np.nan])
    assert last_change_date(d, raw) is None


def test_last_change_single_distinct_value_returns_first_date():
    d = _dates(4)
    raw = pd.Series([5.0, 5.0, 5.0, 5.0])
    assert last_change_date(d, raw) == d.iloc[0].date()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_freshness.py -k last_change -v`
Expected: FAIL — `ImportError: cannot import name 'last_change_date' from 'compute_signals'`

- [ ] **Step 3: Implement the helper**

In `scripts/compute_signals.py`, add after the imports (and add `from datetime import date` / `from typing import Optional` to the import block):

```python
def last_change_date(dates: pd.Series, raw: pd.Series) -> Optional[date]:
    """Date the non-NaN raw value last changed (last day it differed from the
    previous kept value). A single distinct value -> its first date. Empty -> None.

    One rule covers all cadence cases: a monthly signal forward-filled to daily
    lands on its last month boundary; an API-lagged signal (trailing NaN) lands
    on its last real datapoint; a normally-moving daily signal lands on today."""
    s = pd.Series(raw).reset_index(drop=True)
    d = pd.Series(pd.to_datetime(dates)).reset_index(drop=True)
    mask = s.notna()
    s = s[mask].reset_index(drop=True)
    d = d[mask].reset_index(drop=True)
    if len(s) == 0:
        return None
    changed = s.ne(s.shift())          # index 0 is always True (shift -> NaN)
    last_idx = changed[changed].index[-1]
    return d.iloc[last_idx].date()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_freshness.py -k last_change -v`
Expected: PASS (all 5)

- [ ] **Step 5: Write `as_of` into current_signals.json**

In `scripts/compute_signals.py`, inside `_process_asset`, the per-spec loop currently builds:

```python
    for spec in cfg.signals:
        raw, score, sell_score = _last_valid(
            f"{spec.key}_raw", spec.key, f"{spec.key}_sell"
        )
        current["signals"][spec.key] = {
            "raw": _sanitize_float(raw),
            "score": score,
            "sell_score": sell_score,
        }
```

Replace with (adds `as_of`; `signals` is the per-day DataFrame already in scope):

```python
    for spec in cfg.signals:
        raw, score, sell_score = _last_valid(
            f"{spec.key}_raw", spec.key, f"{spec.key}_sell"
        )
        as_of = last_change_date(signals["date"], signals[f"{spec.key}_raw"])
        current["signals"][spec.key] = {
            "raw": _sanitize_float(raw),
            "score": score,
            "sell_score": sell_score,
            "as_of": as_of.isoformat() if as_of is not None else None,
        }
```

- [ ] **Step 6: Regenerate signals and eyeball the output**

Run: `python scripts/compute_signals.py`
Then verify the new field is present:
Run: `python -c "import json; d=json.load(open('data/bitcoin_current_signals.json')); print({k: v.get('as_of') for k,v in d['signals'].items()})"`
Expected: a dict with an ISO date (or null) per signal; `monthly_rsi` should be an earlier (month-boundary) date than the daily signals.

- [ ] **Step 7: Commit**

```bash
git add scripts/compute_signals.py tests/test_freshness.py data/bitcoin_current_signals.json data/ethereum_current_signals.json
git commit -m "feat: compute per-signal as_of (last value-change date)"
```

---

### Task 3: Pass `cadence` + `as_of` through score.py

**Files:**
- Modify: `scripts/score.py` (add `build_signal_entry()`; use it in `_score_asset`)
- Test: `tests/test_freshness.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_freshness.py`:

```python
from score import build_signal_entry, compute_score, SIGNAL_DISPLAY


def test_build_signal_entry_includes_cadence_and_as_of():
    entry = build_signal_entry(
        {"raw": 47.0, "score": 50, "sell_score": 0, "as_of": "2026-05-31"},
        display_name="Monthly RSI", cadence="monthly",
    )
    assert entry["cadence"] == "monthly"
    assert entry["as_of"] == "2026-05-31"
    assert entry["status"] == "neutral"
    assert entry["display_name"] == "Monthly RSI"
    assert entry["score"] == 50


def test_build_signal_entry_status_mapping():
    assert build_signal_entry({"raw": 0, "score": 100}, "x", "daily")["status"] == "buy"
    assert build_signal_entry({"raw": 0, "score": 0}, "x", "daily")["status"] == "avoid"
    assert build_signal_entry({"raw": 0, "score": 50}, "x", "daily")["status"] == "neutral"


def test_build_signal_entry_missing_as_of_is_none():
    entry = build_signal_entry({"raw": 1.0, "score": 100}, "x", "daily")
    assert entry["as_of"] is None
    assert entry["sell_score"] == 0


def test_compute_score_ignores_extra_signal_keys():
    """Regression guard: the math must not react to the new fields."""
    base = {name: {"score": 100} for name in SIGNAL_DISPLAY}
    extra = {name: {"score": 100, "cadence": "daily", "as_of": "2026-06-20", "raw": 1.2}
             for name in SIGNAL_DISPLAY}
    weights = {"signals": {name: {"weight": 1 / 6} for name in SIGNAL_DISPLAY}}
    assert compute_score(base, weights) == compute_score(extra, weights)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_freshness.py -k "build_signal_entry or ignores_extra" -v`
Expected: FAIL — `ImportError: cannot import name 'build_signal_entry' from 'score'` (the `compute_score` regression test will error on the same import).

- [ ] **Step 3: Implement `build_signal_entry` and use it**

In `scripts/score.py`, add this helper above `_score_asset`:

```python
def build_signal_entry(data: dict, display_name: str, cadence: str) -> dict:
    """Assemble one signal's output object for {id}_score.json. Additive: carries
    cadence + as_of through for the dashboard; does not affect any score math."""
    score = data["score"]
    status = "buy" if score == 100 else ("avoid" if score == 0 else "neutral")
    return {
        "display_name": display_name,
        "raw": _sanitize_float(data["raw"]),
        "score": score,
        "sell_score": data.get("sell_score", 0),
        "status": status,
        "cadence": cadence,
        "as_of": data.get("as_of"),
    }
```

Then in `_score_asset`, replace the inline `"signals": { ... }` dict-comprehension in the `output` literal with a call to the helper. Add a cadence lookup just before building `output`:

```python
    cadences = {s.key: s.cadence for s in cfg.signals}
```

and change the `"signals"` entry of `output` from the existing comprehension to:

```python
        "signals": {
            name: build_signal_entry(data, names[name], cadences[name])
            for name, data in current["signals"].items()
        },
```

(`names` is the existing `{s.key: s.display_name}` map already built in `_score_asset`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_freshness.py -v`
Expected: PASS (all tasks-1-3 tests)

- [ ] **Step 5: Regenerate score and verify fields**

Run: `python scripts/score.py`
Run: `python -c "import json; d=json.load(open('data/bitcoin_score.json')); s=d['signals']['monthly_rsi']; print(s['cadence'], s['as_of'])"`
Expected: `monthly 2026-05-31` (or the current month boundary).

- [ ] **Step 6: Commit**

```bash
git add scripts/score.py tests/test_freshness.py data/bitcoin_score.json data/ethereum_score.json
git commit -m "feat: pass cadence + as_of through score.json"
```

---

### Task 4: `next_refresh_date`, `_fmt_md`, `format_freshness` in build_dashboard.py

**Files:**
- Modify: `scripts/build_dashboard.py` (add three helpers; attach `freshness` in `_assemble_asset`)
- Test: `tests/test_freshness.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_freshness.py`:

```python
from build_dashboard import next_refresh_date, format_freshness


def test_next_refresh_mid_month_is_month_end():
    import datetime
    assert next_refresh_date("2026-06-21", "monthly") == datetime.date(2026, 6, 30)


def test_next_refresh_on_month_end_is_same_day():
    import datetime
    assert next_refresh_date("2026-06-30", "monthly") == datetime.date(2026, 6, 30)


def test_next_refresh_daily_is_none():
    assert next_refresh_date("2026-06-21", "daily") is None


def test_format_freshness_daily_current():
    assert format_freshness("daily", "2026-06-20", "2026-06-20") == "Daily · as of Jun 20"


def test_format_freshness_daily_lagging():
    assert format_freshness("daily", "2026-06-18", "2026-06-20") == "Daily · as of Jun 18"


def test_format_freshness_monthly():
    assert format_freshness("monthly", "2026-05-31", "2026-06-21") == \
        "Monthly · as of May 31 · next Jun 30"


def test_format_freshness_no_data_is_cadence_only():
    assert format_freshness("daily", None, "2026-06-20") == "Daily"
    assert format_freshness("monthly", None, "2026-06-20") == "Monthly"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_freshness.py -k "next_refresh or format_freshness" -v`
Expected: FAIL — `ImportError: cannot import name 'next_refresh_date' from 'build_dashboard'`

- [ ] **Step 3: Implement the helpers**

In `scripts/build_dashboard.py`, add after the existing `format_reading` function:

```python
def next_refresh_date(data_date, cadence: str):
    """Date a monthly signal can next change = the month-end on/after the data date.
    Daily signals have no scheduled refresh date -> None."""
    if cadence != "monthly":
        return None
    return (pd.Timestamp(data_date) + pd.offsets.MonthEnd(0)).date()


def _fmt_md(value) -> str:
    """Format a date/ISO-string as 'Mon D' (e.g. 'Jun 20'), no leading zero —
    matches the spark-label style already used in this module."""
    ts = pd.Timestamp(value)
    return f"{ts.strftime('%b')} {ts.day}"


def format_freshness(cadence: str, as_of, data_date) -> str:
    """Muted per-signal caption. Examples:
      Daily   · as of Jun 20
      Monthly · as of May 31 · next Jun 30
    Falls back to the cadence label alone when the signal has no data yet."""
    label = "Monthly" if cadence == "monthly" else "Daily"
    if not as_of:
        return label
    parts = [label, f"as of {_fmt_md(as_of)}"]
    nxt = next_refresh_date(data_date, cadence)
    if nxt is not None:
        parts.append(f"next {_fmt_md(nxt)}")
    return " · ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_freshness.py -k "next_refresh or format_freshness" -v`
Expected: PASS (all 7)

- [ ] **Step 5: Attach `freshness` to each signal blob**

In `scripts/build_dashboard.py`, inside `_assemble_asset`, the per-spec loop currently appends:

```python
        signals.append({
            "key": spec.key,
            "display_name": data["display_name"],
            "reading": format_reading(spec.key, data["raw"]),
            "bar": compute_signal_bar(spec.key, data["raw"], data["score"], signal_meta[spec.key]),
        })
```

Change it to also pass `freshness` (the per-signal `data` now carries `cadence` + `as_of` from score.json; `current_score["date"]` is the data date):

```python
        signals.append({
            "key": spec.key,
            "display_name": data["display_name"],
            "reading": format_reading(spec.key, data["raw"]),
            "bar": compute_signal_bar(spec.key, data["raw"], data["score"], signal_meta[spec.key]),
            "freshness": format_freshness(data.get("cadence", "daily"), data.get("as_of"), current_score["date"]),
        })
```

- [ ] **Step 6: Run tests + rebuild**

Run: `python -m pytest tests/test_freshness.py -v`
Expected: PASS
Run: `python scripts/build_dashboard.py`
Expected: `Dashboard written to docs/index.html ...`

- [ ] **Step 7: Commit**

```bash
git add scripts/build_dashboard.py tests/test_freshness.py docs/index.html notify.json
git commit -m "feat: build per-signal freshness caption string"
```

---

### Task 5: Render the caption line in the template

**Files:**
- Modify: `templates/dashboard.html.j2` (the `metricCardHTML` JS function, ~lines 390-424)

- [ ] **Step 1: Add the caption to the data-bearing card**

In `metricCardHTML`, after the header `</div>` (the flex row containing `display_name` + `reading`) and before the `'<div class="mt-auto w-full">'` block, insert the muted caption. Use inline color `#777` for legibility (lighter than `text-outline` #444, which mockup review showed was too faint):

```javascript
        + '</div>'
        + (sig.freshness ? '<div class="text-[10px] font-data-sm mt-1 mb-1" style="color:#777">' + sig.freshness + '</div>' : '')
        + '<div class="mt-auto w-full">'
```

- [ ] **Step 2: Add the caption to the no-data card branch**

In the early-return branch (when `!b || !b.has_data`), append the caption after the "No data" span so cadence still shows:

```javascript
        return '<div class="bg-surface-charcoal border border-border-subtle rounded-xl p-stack-md flex flex-col">'
          + '<span class="font-label-caps text-label-caps text-on-surface-variant">' + sig.display_name + '</span>'
          + '<span class="font-data-sm text-data-sm text-outline mt-6">No data</span>'
          + (sig.freshness ? '<div class="text-[10px] font-data-sm mt-1" style="color:#777">' + sig.freshness + '</div>' : '')
          + '</div>';
```

- [ ] **Step 3: Rebuild and confirm the string is embedded**

Run: `python scripts/build_dashboard.py`
Run: `python -c "import pathlib,re; h=pathlib.Path('docs/index.html').read_text(encoding='utf-8'); print('freshness token present:', 'sig.freshness' in h)"`
Expected: `freshness token present: True`

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: render per-signal freshness caption on signal cards"
```

---

### Task 6: End-to-end pipeline run, regression guard, and visual check

**Files:** none new — verification only.

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: all tests pass (existing + `tests/test_freshness.py`). No existing test should break — the scoring math is unchanged.

- [ ] **Step 2: Run the full daily pipeline locally**

Run: `python scripts/compute_signals.py && python scripts/score.py && python scripts/build_dashboard.py`
Expected: each step prints its success line; no exceptions.

- [ ] **Step 3: Confirm the composite/spectrum math did not move**

Run: `python -c "import json; d=json.load(open('data/bitcoin_score.json')); print('composite', d['composite_score'], 'spectrum', d['spectrum_pos'], d['spectrum_verdict'])"`
Expected: same `composite_score` / `spectrum_pos` values as before this branch (compare against `git show origin/main:data/bitcoin_score.json` if in doubt). The numbers must be identical — only new per-signal fields were added.

- [ ] **Step 4: Visual check of the caption (legibility)**

Serve and screenshot the built dashboard (file:// is blocked, so use a local server):
```bash
python -m http.server 8899 --bind 127.0.0.1   # run in background
```
Open `http://127.0.0.1:8899/docs/index.html`, screenshot the metric cards, and confirm:
- every card shows one muted caption line under its reading,
- Monthly RSI reads `Monthly · as of <month-end> · next <month-end>`,
- daily signals read `Daily · as of <date>`,
- the `#777` grey is legible on the dark card (bump up slightly if not).
Stop the server when done.

- [ ] **Step 5: Final commit (if the screenshot prompted a color tweak)**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "chore: tune freshness caption legibility per visual check"
```

(If no tweak was needed, skip this commit.)

---

## Notes for the implementer

- **Do not touch** `compute_score`, `compute_spectrum_pos`, weights files, thresholds, or `good_entry`/`good_exit`. This feature is presentation-only.
- `data/*.json` and `docs/index.html` are committed artifacts in this repo (the daily CI commits them), so regenerating and committing them per task is expected, not accidental.
- The `as_of` rule is **last value-change**, never **last non-NaN** — the latter silently breaks Monthly RSI (its forward-filled series is never NaN). The tests in Task 2 lock this in.
