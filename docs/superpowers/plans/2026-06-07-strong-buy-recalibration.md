# STRONG BUY Recalibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the spectrum "STRONG BUY" headline a rare, per-asset-calibrated flag (Bitcoin cutoff 85, Ethereum cutoff 88) instead of the current loose global 80.

**Architecture:** Introduce a `strong_buy_cutoff` field on `AssetConfig` (default 85). `scripts/score.py` uses it to label the spectrum verdict and writes it into `{asset}_score.json`. `scripts/build_dashboard.py` reads it for the "distance" copy and embeds it in the per-asset JSON. `templates/dashboard.html.j2` reads the embedded cutoff so the gauge green zone and chart bands follow the label. No signal weights, signal thresholds, or spectrum formula change.

**Tech Stack:** Python 3, pandas, pytest, Jinja2 template rendering, vanilla JS in the dashboard template.

**Spec:** `docs/superpowers/specs/2026-06-07-strong-buy-recalibration-design.md`

---

## File Structure

- `assets/base.py` — add `strong_buy_cutoff: float = 85.0` to `AssetConfig`.
- `assets/eth.py` — set `strong_buy_cutoff=88.0` in `CONFIG`.
- `scripts/score.py` — `get_spectrum_verdict` takes a cutoff; `_score_asset` passes `cfg.strong_buy_cutoff` and writes it into the score JSON.
- `scripts/build_dashboard.py` — `distance_text` uses the asset cutoff; `_assemble_asset` adds `strong_buy_cutoff` to the payload dict.
- `templates/dashboard.html.j2` — `zoneColor`, `zoneIndex`, and the chart `zoneBands` plugin read the asset cutoff (default 85).
- `tests/test_sell_signal.py` — band-edge tests for `get_spectrum_verdict` with explicit cutoffs.
- `tests/test_framework.py` — assert `strong_buy_cutoff` defaults (BTC 85, ETH 88).
- `tests/test_push.py` — keep the STRONG BUY fixture self-consistent (spectrum ≥ cutoff).

---

## Task 1: Add `strong_buy_cutoff` to AssetConfig and set ETH to 88

**Files:**
- Modify: `assets/base.py:22-34`
- Modify: `assets/eth.py:133-169` (CONFIG)
- Modify: `assets/bitcoin.py:152-182` (CONFIG — explicit 85 for clarity)
- Test: `tests/test_framework.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_framework.py`:

```python
def test_strong_buy_cutoff_defaults():
    from assets.base import AssetConfig
    import dataclasses
    # default on the dataclass field is 85.0
    fields = {f.name: f for f in dataclasses.fields(AssetConfig)}
    assert fields["strong_buy_cutoff"].default == 85.0


def test_asset_strong_buy_cutoffs():
    from assets.bitcoin import CONFIG as BTC
    from assets.eth import CONFIG as ETH
    assert BTC.strong_buy_cutoff == 85.0
    assert ETH.strong_buy_cutoff == 88.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_framework.py::test_strong_buy_cutoff_defaults tests/test_framework.py::test_asset_strong_buy_cutoffs -v`
Expected: FAIL — `AssetConfig` has no field `strong_buy_cutoff` (KeyError / AttributeError).

- [ ] **Step 3: Add the field and set values**

In `assets/base.py`, add the field to `AssetConfig` after the existing optional fields (keep it after the other defaulted fields so dataclass ordering stays valid):

```python
    weight_overrides: Optional[dict[str, float]] = None
    sell_weight_overrides: Optional[dict[str, float]] = None
    strong_buy_cutoff: float = 85.0   # spectrum_pos at/above which headline reads STRONG BUY
```

In `assets/bitcoin.py`, inside `CONFIG = AssetConfig(...)`, add an explicit value (next to `weight_overrides`):

```python
    weight_overrides={"mvrv_zscore": 2.0},
    strong_buy_cutoff=85.0,
```

In `assets/eth.py`, inside `CONFIG = AssetConfig(...)`, add:

```python
    weight_overrides=None,   # start neutral; calibration/validation decides any boost
    strong_buy_cutoff=88.0,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_framework.py::test_strong_buy_cutoff_defaults tests/test_framework.py::test_asset_strong_buy_cutoffs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add assets/base.py assets/bitcoin.py assets/eth.py tests/test_framework.py
git commit -m "feat: add per-asset strong_buy_cutoff (BTC 85, ETH 88)"
```

---

## Task 2: Thread cutoff through score.py and emit it in score.json

**Files:**
- Modify: `scripts/score.py:47-56` (`get_spectrum_verdict`)
- Modify: `scripts/score.py:124-148` (`_score_asset`)
- Test: `tests/test_sell_signal.py:210-217`

- [ ] **Step 1: Update the failing test**

Replace `test_get_spectrum_verdict` in `tests/test_sell_signal.py` with:

```python
def test_get_spectrum_verdict():
    from score import get_spectrum_verdict
    # default cutoff = 85
    assert get_spectrum_verdict(10)  == "TAKE PROFIT"
    assert get_spectrum_verdict(20)  == "SELL"
    assert get_spectrum_verdict(40)  == "HOLD"
    assert get_spectrum_verdict(60)  == "BUY"
    assert get_spectrum_verdict(84)  == "BUY"           # below default cutoff
    assert get_spectrum_verdict(85)  == "STRONG BUY"    # at default cutoff
    assert get_spectrum_verdict(100) == "STRONG BUY"


def test_get_spectrum_verdict_custom_cutoff():
    from score import get_spectrum_verdict
    # ETH-style cutoff = 88
    assert get_spectrum_verdict(87, cutoff=88) == "BUY"
    assert get_spectrum_verdict(88, cutoff=88) == "STRONG BUY"
    # lower bands unaffected by cutoff
    assert get_spectrum_verdict(60, cutoff=88) == "BUY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sell_signal.py::test_get_spectrum_verdict tests/test_sell_signal.py::test_get_spectrum_verdict_custom_cutoff -v`
Expected: FAIL — `get_spectrum_verdict` takes no `cutoff` arg / `get_spectrum_verdict(85)` still returns "STRONG BUY" but `get_spectrum_verdict(84)` returns "STRONG BUY" (old threshold 80).

- [ ] **Step 3: Update `get_spectrum_verdict`**

In `scripts/score.py`, replace the function:

```python
def get_spectrum_verdict(spectrum_pos: float, cutoff: float = 85.0) -> str:
    if spectrum_pos >= cutoff:
        return "STRONG BUY"
    if spectrum_pos >= 60:
        return "BUY"
    if spectrum_pos >= 40:
        return "HOLD"
    if spectrum_pos >= 20:
        return "SELL"
    return "TAKE PROFIT"
```

- [ ] **Step 4: Pass the asset cutoff and emit it in the output**

In `scripts/score.py` `_score_asset`, update the verdict call and the output dict.

Change:

```python
    spectrum_verdict = get_spectrum_verdict(spectrum_pos)
```

to:

```python
    spectrum_verdict = get_spectrum_verdict(spectrum_pos, cfg.strong_buy_cutoff)
```

In the `output = {...}` dict, add the cutoff right after `spectrum_verdict`:

```python
        "spectrum_pos": spectrum_pos,
        "spectrum_verdict": spectrum_verdict,
        "strong_buy_cutoff": cfg.strong_buy_cutoff,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_sell_signal.py -v`
Expected: PASS (all spectrum tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/score.py tests/test_sell_signal.py
git commit -m "feat: score uses per-asset strong_buy_cutoff and emits it"
```

---

## Task 3: build_dashboard reads the cutoff for copy + payload

**Files:**
- Modify: `scripts/build_dashboard.py:283-292` (`distance_text`)
- Modify: `scripts/build_dashboard.py:308-324` (`_assemble_asset` return dict)
- Test: `tests/test_build_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_build_dashboard.py` (imports `build_dashboard` as the others in that file do — match the existing import style at the top of the file):

```python
def test_assemble_asset_includes_strong_buy_cutoff(tmp_path, monkeypatch):
    # The assembled asset payload must surface the asset's strong_buy_cutoff
    # so the template can render the gauge zones from it.
    import scripts.build_dashboard as bd
    from assets.eth import CONFIG as ETH
    # _assemble_asset reads {id}_score.json etc.; assert the field is wired by
    # checking the score-JSON key is propagated. If _assemble_asset requires
    # data files, assert via the cutoff default fallback helper instead:
    assert ETH.strong_buy_cutoff == 88.0
```

> Note: if `_assemble_asset` is hard to unit-test without data fixtures, keep this as the lightweight assertion above and rely on Task 5's end-to-end regeneration to verify the payload. Do NOT build elaborate fixtures here.

- [ ] **Step 2: Run test to verify it fails or passes trivially**

Run: `python -m pytest tests/test_build_dashboard.py::test_assemble_asset_includes_strong_buy_cutoff -v`
Expected: PASS trivially (it asserts the config value). The real wiring is verified end-to-end in Task 5.

- [ ] **Step 3: Update `distance_text` to use the cutoff**

In `scripts/build_dashboard.py`, the `_assemble_asset` function has `cfg` in scope. Replace the `distance_text` block:

```python
    cutoff = cfg.strong_buy_cutoff
    if spectrum_pos >= cutoff:
        distance_text = "Strong Buy zone"
    elif spectrum_pos >= 60:
        distance_text = f"{cutoff - spectrum_pos:.1f} pts from Strong Buy"
    elif spectrum_pos >= 40:
        distance_text = f"{60 - spectrum_pos:.1f} pts from Buy zone"
    elif spectrum_pos >= 20:
        distance_text = f"{spectrum_pos - 20:.1f} pts into Sell zone"
    else:
        distance_text = "Take profit zone"
```

- [ ] **Step 4: Add `strong_buy_cutoff` to the payload dict**

In the `_assemble_asset` `return {...}` dict, add after `spectrum_verdict`:

```python
        "spectrum_pos":     spectrum_pos,
        "spectrum_verdict": spectrum_verdict,
        "strong_buy_cutoff": cfg.strong_buy_cutoff,
```

- [ ] **Step 5: Run the build_dashboard test suite**

Run: `python -m pytest tests/test_build_dashboard.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/build_dashboard.py tests/test_build_dashboard.py
git commit -m "feat: build_dashboard reads strong_buy_cutoff for copy and payload"
```

---

## Task 4: Template gauge + chart bands follow the cutoff

**Files:**
- Modify: `templates/dashboard.html.j2:230-237` (`zoneColor`, `zoneIndex`)
- Modify: `templates/dashboard.html.j2:436-441` (chart `zoneBands` plugin)

No standalone unit test (template JS isn't unit-tested in this repo); verified visually/end-to-end in Task 5.

- [ ] **Step 1: Make `zoneColor` and `zoneIndex` take a cutoff**

In `templates/dashboard.html.j2`, replace the two helpers:

```javascript
    function zoneColor(s, cutoff) {
      var sb = cutoff || 85;
      return s >= sb ? '#00ff88' : s >= 60 ? '#00C853' : s >= 40 ? '#D0D0D0' : s >= 20 ? '#ff9800' : '#FF3B30';
    }
    // Which of the 5 spectrum zones a position falls in (0=TP .. 4=Strong Buy)
    function zoneIndex(pos, cutoff) {
      var sb = cutoff || 85;
      return pos >= sb ? 4 : pos >= 60 ? 3 : pos >= 40 ? 2 : pos >= 20 ? 1 : 0;
    }
```

- [ ] **Step 2: Pass the asset cutoff at every call site**

Find all call sites of `zoneColor(` and `zoneIndex(` in the template and pass the asset's cutoff. The asset object (commonly `a` or `d`) carries `strong_buy_cutoff`.

Run: `grep -n "zoneColor(\|zoneIndex(" templates/dashboard.html.j2`

For each call where an asset object is in scope (e.g. `zoneIndex(a.spectrum_pos)` → `zoneIndex(a.spectrum_pos, a.strong_buy_cutoff)`, `zoneColor(a.spectrum_pos)` → `zoneColor(a.spectrum_pos, a.strong_buy_cutoff)`). If a call site has the detail object `d`, use `d.strong_buy_cutoff`.

- [ ] **Step 3: Make the chart `zoneBands` use the cutoff**

In `renderChart(d)`, replace the hardcoded top two bands. Add a local at the top of the `beforeDraw` array construction and use it:

```javascript
          var sb = (d && d.strong_buy_cutoff) || 85;
          [
            { min: sb, max: 100, color: '#00ff8810' },
            { min: 60, max: sb,  color: '#00C85310' },
            { min: 40, max: 60,  color: '#ffffff08' },
            { min: 20, max: 40,  color: '#ff980010' },
            { min: 0,  max: 20,  color: '#FF3B3010' },
          ].forEach(function (z) {
```

(If `d` is not in scope inside `beforeDraw`, hoist `var sb = (d && d.strong_buy_cutoff) || 85;` to the top of `renderChart(d)` and reference it.)

- [ ] **Step 4: Sanity-check the template still renders**

Run: `python -c "import scripts.build_dashboard as bd"` (import smoke test; full render happens in Task 5).
Expected: no import error.

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html.j2
git commit -m "feat: gauge zones and chart bands follow strong_buy_cutoff"
```

---

## Task 5: Regenerate data, verify behavior end-to-end, full suite

**Files:**
- Regenerated: `data/bitcoin_score.json`, `data/ethereum_score.json`, `docs/index.html`

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: all tests PASS (≈ 82 with the new ones).

- [ ] **Step 2: Regenerate signals, scores, and dashboard**

Run:
```bash
python scripts/compute_signals.py
python scripts/score.py
python scripts/build_dashboard.py
```
Expected: no errors; score.py prints spectrum verdicts.

- [ ] **Step 3: Verify the headline verdicts flipped**

Run:
```bash
python -c "import json; d=json.load(open('data/bitcoin_score.json')); print('BTC', d['spectrum_pos'], d['spectrum_verdict'], d.get('strong_buy_cutoff'))"
python -c "import json; d=json.load(open('data/ethereum_score.json')); print('ETH', d['spectrum_pos'], d['spectrum_verdict'], d.get('strong_buy_cutoff'))"
```
Expected:
- BTC: `spectrum_pos` 83.1, `spectrum_verdict` **BUY** (was STRONG BUY), `strong_buy_cutoff` 85.0
- ETH: `spectrum_pos` 87.7, `spectrum_verdict` **BUY** (was STRONG BUY), `strong_buy_cutoff` 88.0

> Note: exact spectrum_pos values may differ slightly if the daily data refreshed; what matters is that each is below its cutoff and now reads BUY.

- [ ] **Step 4: Verify the embedded cutoff reached the dashboard HTML**

Run: `grep -o '"strong_buy_cutoff": *8[58]' docs/index.html | sort | uniq -c`
Expected: both 85 (BTC) and 88 (ETH) present in the embedded `ASSETS` JSON.

- [ ] **Step 5: Commit regenerated artifacts**

```bash
git add data/bitcoin_score.json data/ethereum_score.json docs/index.html
git commit -m "chore: regenerate scores/dashboard with recalibrated strong_buy_cutoff"
```

---

## Self-Review Notes

- **Spec coverage:** config field (Task 1), score logic + emit (Task 2), build_dashboard copy + payload (Task 3), template gauge + chart bands (Task 4), regeneration + verification (Task 5). Non-goals (composite verdict, weights) are untouched.
- **Type consistency:** field name `strong_buy_cutoff` used identically across base.py, bitcoin.py, eth.py, score.py output, build_dashboard payload, and template (`a.strong_buy_cutoff` / `d.strong_buy_cutoff`). `get_spectrum_verdict(spectrum_pos, cutoff=85.0)` signature consistent between definition and call site.
- **Backward compatibility:** every consumer defaults to 85 when the field/key is absent (`get_spectrum_verdict` default arg, template `|| 85`, build_dashboard reads from `cfg` directly).
