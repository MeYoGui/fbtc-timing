# BTC Model Fixes — Historical Validation Experiment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove (or disprove) on historical BTC data that three model corrections — leak-fixed walk-forward labels, causal expanding-window MVRV z-score, and continuous signal scoring — improve out-of-sample timing before any production code changes.

**Architecture:** A self-contained experiment harness (`scripts/experiment.py`) rebuilds signal histories from `data/bitcoin_history.csv` under variant flags, runs every variant through the same leak-fixed walk-forward, and emits a comparison report. Production files (`data/*_score.json`, `data/*_weights.json`, dashboard) are never touched. New pure functions (expanding z-score, continuous score) are added *additively* to shared modules with unit tests, but nothing wires them into the daily pipeline. A pre-registered decision rule turns the report into an adopt/reject verdict; productionization is a separate Phase B plan written only after the gate.

**Tech Stack:** Python, pandas, numpy, pytest (already in use — no new dependencies).

## Global Constraints

- **No production writes:** the experiment writes only under `data/experiments/`; it must never modify `data/bitcoin_*.json`, `data/bitcoin_*.csv`, or anything ETH.
- **No new dependencies:** pandas/numpy only (Spearman via `pandas.Series.corr(method="spearman")`, not scipy).
- **BTC only:** ETH is out of scope for Phase A entirely.
- **Pre-registered constants (do not tune during execution):** `MIN_PERIODS_Z = 365`, coverage levels `[0.05, 0.10]`, walk-forward `STEP_DAYS = 90`, `WARMUP_DAYS = 365*4`, `HOLDING_DAYS = 548` (all reused from `scripts/validate_composite.py` where they exist).
- **Pre-registered decision rule (Task 6):** correctness fixes (leak-fixed labels, causal z) are adopted unconditionally; improvement variants (continuous scoring, family weights) are adopted only if they beat the causal baseline per the metrics in Task 6, evaluated once — no iterating on the rule after seeing results.
- All commands run from the repo root `C:\Users\guill\Workspace\fbtc-timing`.

---

### Task 1: Experiment harness skeleton + legacy parity check

The harness must first reproduce the existing pipeline's out-of-sample numbers exactly. If it can't, every later comparison is meaningless.

**Adversarial-review note:** the committed `bitcoin_validation.json` (edge `-0.4778`) was generated ~2026-06-04, but the CSVs have grown daily since — re-running the same code on current data produces slightly different numbers. Parity must therefore be checked against a FRESHLY regenerated validation file, not the stale committed one. Step 5 regenerates it first.

**Files:**
- Create: `scripts/experiment.py`
- Create: `tests/test_experiment.py`
- Create: `data/experiments/` (output dir; created by the script)

**Interfaces:**
- Consumes: `validate_composite.walk_forward`, `validate_composite.timing_edge`, `validate_composite.invest_precision`, `validate_composite.band_report`, `validate_composite.forward_returns`, `validate_composite._good_aligned_to`, `backtest.compute_signal_stats`, `backtest.derive_weights`, `assets.bitcoin.CONFIG`
- Produces: `run_legacy_parity() -> dict` (metrics dict with keys `timing_edge`, `invest_precision`, `bands`), `evaluate(oos: pd.Series, eval_good: pd.Series, fwd: pd.Series, dates: pd.Series) -> dict`, `edge_at_coverage(oos, fwd, pct) -> dict`, `precision_at_coverage(oos, eval_good, pct) -> dict`, `edge_by_cycle(oos, fwd, dates, pct) -> dict`

- [ ] **Step 1: Write failing tests for the two evaluation metrics**

In `tests/test_experiment.py`:

```python
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from experiment import edge_at_coverage, edge_by_cycle, precision_at_coverage


def test_precision_at_coverage_counts_good_entries_in_top_days():
    # top 50% of 4 scored days = 2 days (composite 100 and 90); one is a good entry
    oos = pd.Series([100.0, 90.0, 10.0, 20.0])
    good = pd.Series([True, False, True, False])
    out = precision_at_coverage(oos, good, pct=0.50)
    assert out["coverage_days"] == 2
    assert out["precision"] == pytest.approx(0.5)


def test_precision_at_coverage_ignores_nan_composite_rows():
    oos = pd.Series([np.nan, 100.0, 50.0])
    good = pd.Series([True, True, False])
    out = precision_at_coverage(oos, good, pct=0.50)
    assert out["coverage_days"] == 1        # 2 scored rows -> top 50% = 1
    assert out["precision"] == pytest.approx(1.0)


def test_edge_at_coverage_picks_top_composite_days():
    # 10 days; composite ranks day 9 highest; its fwd return is 1.0 vs mean 0.1
    oos = pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
    fwd = pd.Series([0.0] * 9 + [1.0])
    out = edge_at_coverage(oos, fwd, pct=0.10)
    assert out["coverage_days"] == 1
    assert out["top_mean_fwd"] == 1.0
    assert out["edge"] == pytest.approx(1.0 - 0.1)


def test_edge_at_coverage_ignores_nan_rows():
    oos = pd.Series([np.nan, np.nan, 50.0, 100.0])
    fwd = pd.Series([9.9, 9.9, 0.0, 1.0])
    out = edge_at_coverage(oos, fwd, pct=0.50)
    # only 2 scored rows; top 50% = 1 day = the composite-100 day
    assert out["coverage_days"] == 1
    assert out["top_mean_fwd"] == 1.0


def test_edge_by_cycle_buckets_by_halving():
    dates = pd.Series(pd.to_datetime(["2013-06-01", "2013-07-01",
                                      "2017-06-01", "2017-07-01"]))
    oos = pd.Series([100.0, 0.0, 100.0, 0.0])
    fwd = pd.Series([0.5, 0.1, 0.2, 0.0])
    out = edge_by_cycle(oos, fwd, dates, pct=0.50)
    # one bucket per halving cycle present in the data
    assert set(out) == {"2012-11-28", "2016-07-09"}
    assert out["2012-11-28"]["edge"] == pytest.approx(0.5 - 0.3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_experiment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'experiment'`

- [ ] **Step 3: Write the harness skeleton with metrics + legacy parity**

Create `scripts/experiment.py`:

```python
"""Offline A/B experiment: compare model-fix variants on historical BTC data.

Reads data/bitcoin_history.csv (and the stored signal history for the parity
check) but writes ONLY under data/experiments/ — never the production JSON/CSV.

Stages (see Task 6):
  legacy   — original leaky walk-forward on stored signals (parity check)
  stage1   — leak-fixed labels, original features, ternary scores (honest baseline)
  stage1c  — stage1 + causal expanding MVRV z-score (correctness baseline)
  stage2   — stage1c + {continuous scoring} x {family weights} grid

Primary metric: coverage-matched OOS edge (top-10% composite days), because
verdict-band cutoffs are not comparable between ternary and continuous scores.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from assets import bitcoin
from backtest import compute_signal_stats, derive_weights
from validate_composite import (
    HOLDING_DAYS, STEP_DAYS, WARMUP_DAYS,
    band_report, composite_series, forward_returns, invest_precision,
    timing_edge, walk_forward, _good_aligned_to,
)

DATA_DIR = Path(__file__).parent.parent / "data"
OUT_DIR = DATA_DIR / "experiments"

MIN_PERIODS_Z = 365           # pre-registered; not tuned
COVERAGE_PCTS = [0.05, 0.10]  # pre-registered coverage levels


def edge_at_coverage(oos: pd.Series, fwd: pd.Series, pct: float) -> dict:
    """Mean forward return of the top pct fraction of scored days, by composite,
    minus the mean over all scored days. Coverage-matched: comparable across
    variants whose composite distributions differ (ternary vs continuous)."""
    d = pd.DataFrame({"c": oos.values, "fwd": fwd.values}).dropna()
    if d.empty:
        return {"coverage_days": 0, "top_mean_fwd": None, "all_mean_fwd": None, "edge": None}
    k = max(1, int(len(d) * pct))
    top = d.nlargest(k, "c")["fwd"]
    return {
        "coverage_days": k,
        "top_mean_fwd": round(float(top.mean()), 4),
        "all_mean_fwd": round(float(d["fwd"].mean()), 4),
        "edge": round(float(top.mean() - d["fwd"].mean()), 4),
    }


def precision_at_coverage(oos: pd.Series, eval_good: pd.Series, pct: float) -> dict:
    """Fraction of the top pct composite days that are hindsight good entries.
    Coverage-matched replacement for precision@60: a fixed composite cutoff
    selects different day counts under ternary vs continuous scoring, so it
    can't compare variants fairly; a fixed coverage can."""
    d = pd.DataFrame({"c": oos.values, "good": eval_good.values}).dropna(subset=["c"])
    if d.empty:
        return {"coverage_days": 0, "precision": None}
    k = max(1, int(len(d) * pct))
    top = d.nlargest(k, "c")["good"].astype(bool)
    return {"coverage_days": k, "precision": round(float(top.mean()), 4)}


def edge_by_cycle(oos: pd.Series, fwd: pd.Series, dates: pd.Series, pct: float = 0.10) -> dict:
    """edge_at_coverage computed inside each halving cycle separately, so a
    composite that only 'worked' in one era is visible. Keyed by cycle start."""
    halvings = pd.to_datetime(bitcoin.HALVING_DATES)
    d = pd.DataFrame({
        "c": oos.values, "fwd": fwd.values,
        "date": pd.to_datetime(pd.Series(dates).values),
    }).dropna()
    d["cycle"] = pd.cut(d["date"], bins=halvings, labels=bitcoin.HALVING_DATES[:-1], right=False)
    out = {}
    for cycle_start, sub in d.groupby("cycle", observed=True):
        if len(sub) == 0:
            continue
        out[str(cycle_start)] = edge_at_coverage(
            sub["c"].reset_index(drop=True), sub["fwd"].reset_index(drop=True), pct)
    return out


def evaluate(oos: pd.Series, eval_good: pd.Series, fwd: pd.Series, dates: pd.Series) -> dict:
    """Full metric set for one variant run. eval_good may use hindsight — ground
    truth for EVALUATION is allowed to know the future; TRAINING labels are not."""
    scored = oos.notna()
    d = pd.DataFrame({"c": oos.values, "fwd": fwd.values}).dropna()
    ic = d["c"].corr(d["fwd"], method="spearman") if len(d) > 2 else None
    return {
        "scored_days": int(scored.sum()),
        "timing_edge_at60": timing_edge(oos, fwd),
        "invest_precision_at60": invest_precision(oos[scored], eval_good[scored]),
        "spearman_ic": round(float(ic), 4) if ic is not None and np.isfinite(ic) else None,
        "edge_at_coverage": {str(p): edge_at_coverage(oos, fwd, p) for p in COVERAGE_PCTS},
        "precision_at_coverage": {str(p): precision_at_coverage(oos, eval_good, p)
                                  for p in COVERAGE_PCTS},
        "edge_by_cycle_10pct": edge_by_cycle(oos, fwd, dates, 0.10),
        "bands": band_report(oos, fwd),
    }


def load_btc() -> tuple:
    price_df = pd.read_csv(DATA_DIR / "bitcoin_history.csv")
    price_df["date"] = pd.to_datetime(price_df["date"])
    signals_df = pd.read_csv(DATA_DIR / "bitcoin_signal_history.csv")
    signals_df["date"] = pd.to_datetime(signals_df["date"])
    return price_df, signals_df


def run_legacy_parity() -> dict:
    """Re-run the ORIGINAL (leaky) walk-forward on the stored signal history.
    Must reproduce data/bitcoin_validation.json's out_of_sample block exactly."""
    cfg = bitcoin.CONFIG
    price_df, signals_df = load_btc()
    signal_names = [s.key for s in cfg.signals]
    merged = price_df[["date", "price"]].merge(signals_df, on="date", how="inner").reset_index(drop=True)
    fwd = forward_returns(merged["price"])
    oos, good = walk_forward(price_df, signals_df, cfg, signal_names)
    scored = oos.notna()
    return {
        "timing_edge": timing_edge(oos, fwd),
        "invest_precision": invest_precision(oos[scored], good[scored]),
        "bands": band_report(oos, fwd),
    }


def main():
    OUT_DIR.mkdir(exist_ok=True)
    stored = json.loads((DATA_DIR / "bitcoin_validation.json").read_text())["out_of_sample"]
    parity = run_legacy_parity()
    match = (
        parity["timing_edge"]["edge"] == stored["timing_edge"]["edge"]
        and parity["invest_precision"]["precision"] == stored["invest_precision"]["precision"]
    )
    print(f"legacy parity: edge={parity['timing_edge']['edge']} "
          f"(stored {stored['timing_edge']['edge']}) -> {'PASS' if match else 'FAIL'}")
    (OUT_DIR / "legacy_parity.json").write_text(json.dumps(parity, indent=2))
    if not match:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_experiment.py -v`
Expected: 3 PASS

- [ ] **Step 5: Regenerate the reference validation, then run the parity check**

Run: `python scripts/validate_composite.py`
Expected: prints one `... OOS edge=... precision=... -> PASS|REVIEW` line per asset and rewrites `data/bitcoin_validation.json` / `data/ethereum_validation.json`. This is the existing script doing its normal job (the refreshed numbers will differ slightly from the committed file because the CSVs grew since 2026-06-04) — commit it separately in Step 6 so the diff is auditable.

Run: `python scripts/experiment.py`
Expected output: `legacy parity: edge=<X> (stored <X>) -> PASS` where `<X>` matches the freshly printed bitcoin OOS edge exactly; exit code 0; `data/experiments/legacy_parity.json` created.

If FAIL: stop and debug (systematic-debugging skill) — do not proceed to Task 2 with a harness that cannot reproduce known numbers.

- [ ] **Step 6: Commit (validation refresh separate from harness)**

```bash
git add data/bitcoin_validation.json data/ethereum_validation.json
git commit -m "chore: refresh validation reports on current history"
git add scripts/experiment.py tests/test_experiment.py data/experiments/legacy_parity.json
git commit -m "feat(experiment): harness skeleton with coverage/cycle metrics + legacy parity check"
```

---

### Task 2: Leak-fixed walk-forward (training labels recomputed per window)

`validate_composite.walk_forward` computes `good_entry` ONCE on the full price
history. `_get_cycle_ranges` gives completed cycles their eventual full-cycle
low/high, so training rows in a then-ongoing cycle are labeled with information
from that cycle's future. The fix: at each step `t`, recompute labels from
`price_df.iloc[:t]` — only prices known at decision time.

**Files:**
- Modify: `scripts/experiment.py` (add `walk_forward_fixed`)
- Modify: `tests/test_experiment.py` (add causality test)

**Interfaces:**
- Consumes: `compute_signal_stats`, `derive_weights`, `composite_series` (existing signatures)
- Produces: `walk_forward_fixed(price_df, signals_df, cfg, signal_names, weight_fn=None, step_days=STEP_DAYS) -> pd.Series` (OOS composite, NaN outside scored windows). `weight_fn: Callable[[list[str]], dict[str, float]] | None` — when given, replaces precision-derived weights (used by Task 5).

- [ ] **Step 1: Write the failing causality test**

Append to `tests/test_experiment.py`:

```python
from experiment import walk_forward_fixed
from validate_composite import walk_forward
from assets import bitcoin


def _synthetic_market(n=4000, spike_at=None):
    """Price series spanning 2012-2023 with cycle-ish waves. Optionally a 10x
    spike after index spike_at to move the eventual cycle high."""
    dates = pd.date_range("2012-01-01", periods=n, freq="D")
    t = np.arange(n)
    price = 100 * np.exp(t / 900) * (1.3 + np.sin(t / 250))
    if spike_at is not None:
        price = price.copy()
        price[spike_at:] *= 10
    price_df = pd.DataFrame({"date": dates, "price": price})
    rng = np.random.default_rng(7)
    signals_df = pd.DataFrame({
        "date": dates,
        "sig_a": rng.choice([0, 50, 100], size=n).astype(float),
        "sig_b": rng.choice([0, 50, 100], size=n).astype(float),
    })
    return price_df, signals_df


class _Cfg:
    good_entry = staticmethod(bitcoin.good_entry)
    weight_overrides = None


def test_walk_forward_fixed_is_causal_where_legacy_is_not():
    """Changing prices after index k must not change OOS scores at indices < k."""
    k = 3000
    names = ["sig_a", "sig_b"]
    base_p, base_s = _synthetic_market()
    spike_p, _ = _synthetic_market(spike_at=k)

    fixed_base = walk_forward_fixed(base_p, base_s, _Cfg, names)
    fixed_spike = walk_forward_fixed(spike_p, base_s, _Cfg, names)
    pd.testing.assert_series_equal(fixed_base.iloc[:k], fixed_spike.iloc[:k])

    legacy_base, _ = walk_forward(base_p, base_s, _Cfg, names)
    legacy_spike, _ = walk_forward(spike_p, base_s, _Cfg, names)
    assert not legacy_base.iloc[:k].equals(legacy_spike.iloc[:k]), (
        "legacy walk_forward unexpectedly causal — synthetic spike too weak, "
        "or the leak was already fixed upstream"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment.py::test_walk_forward_fixed_is_causal_where_legacy_is_not -v`
Expected: FAIL with `ImportError: cannot import name 'walk_forward_fixed'`

- [ ] **Step 3: Implement walk_forward_fixed**

Add to `scripts/experiment.py`:

```python
def walk_forward_fixed(price_df, signals_df, cfg, signal_names,
                       weight_fn=None, step_days=STEP_DAYS) -> pd.Series:
    """Leak-fixed walk-forward. Difference vs validate_composite.walk_forward:
    good-entry TRAINING labels are recomputed at each step from prices known at
    decision time t (price_df.iloc[:t]), so cycle-range stats cannot leak a
    cycle's eventual high/low into weights. weight_fn, when given, bypasses
    precision weighting entirely (fixed-weight variants)."""
    merged = price_df[["date", "price"]].merge(
        signals_df, on="date", how="inner").reset_index(drop=True)
    assert len(merged) == len(price_df), "signals must align 1:1 with price history"
    n = len(merged)
    oos = pd.Series(np.nan, index=merged.index)
    t = WARMUP_DAYS
    while t < n - HOLDING_DAYS:
        cutoff = t - HOLDING_DAYS
        if cutoff >= WARMUP_DAYS // 2:
            if weight_fn is not None:
                weights = weight_fn(signal_names)
            else:
                known = price_df.iloc[:t].reset_index(drop=True)
                good_known = cfg.good_entry(known)   # causal: prices < t only
                train = merged.iloc[:cutoff]
                train_good = good_known.iloc[:cutoff]
                stats = compute_signal_stats(train, train_good, signal_names)
                weights = derive_weights(
                    stats, signal_names, getattr(cfg, "weight_overrides", None))
            wdict = {"signals": {s: {"weight": weights[s]} for s in signal_names}}
            oos.iloc[t:t + step_days] = composite_series(
                merged.iloc[t:t + step_days], wdict, signal_names).values
        t += step_days
    return oos
```

- [ ] **Step 4: Run all experiment tests**

Run: `python -m pytest tests/test_experiment.py -v`
Expected: all PASS (the causality test takes ~30-60s — good_entry is recomputed per step)

- [ ] **Step 5: Commit**

```bash
git add scripts/experiment.py tests/test_experiment.py
git commit -m "feat(experiment): leak-fixed walk-forward with per-window causal labels"
```

---

### Task 3: Causal expanding-window MVRV z-score

`compute_mvrv_zscore` normalizes with full-history mean/std — the 2015 score
"knows" 2021. Add an expanding-window version, additively, in the shared module.

**Files:**
- Modify: `assets/signals.py` (append function; touch nothing existing)
- Modify: `tests/test_signals.py` (append tests)

**Interfaces:**
- Produces: `compute_mvrv_zscore_expanding(df: pd.DataFrame, min_periods: int = 365) -> pd.Series` — NaN for the first `min_periods-1` rows; consumed by the harness (Task 6) and later by Phase B.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_signals.py`:

```python
def test_expanding_zscore_is_truncation_invariant():
    """Value at row i must not change when future rows are removed — the
    property the full-history z-score violates."""
    from assets.signals import compute_mvrv_zscore_expanding
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"mvrv": rng.normal(2.0, 0.8, size=1200)})
    full = compute_mvrv_zscore_expanding(df, min_periods=100)
    trunc = compute_mvrv_zscore_expanding(df.iloc[:600].copy(), min_periods=100)
    pd.testing.assert_series_equal(full.iloc[:600], trunc)


def test_expanding_zscore_warmup_is_nan():
    from assets.signals import compute_mvrv_zscore_expanding
    df = pd.DataFrame({"mvrv": np.linspace(1.0, 3.0, 200)})
    z = compute_mvrv_zscore_expanding(df, min_periods=100)
    assert z.iloc[:99].isna().all()
    assert z.iloc[99:].notna().all()


def test_expanding_zscore_known_value():
    from assets.signals import compute_mvrv_zscore_expanding
    df = pd.DataFrame({"mvrv": [1.0, 2.0, 3.0, 6.0]})
    z = compute_mvrv_zscore_expanding(df, min_periods=3)
    # at row 3: history [1,2,3,6] -> mean 3.0, std (sample) ~2.1602
    assert z.iloc[3] == pytest.approx((6.0 - 3.0) / 2.160246899469287)
```

(If `tests/test_signals.py` lacks `numpy as np` / `pandas as pd` / `pytest` imports at top, add them.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_signals.py -k expanding -v`
Expected: 3 FAIL with `ImportError: cannot import name 'compute_mvrv_zscore_expanding'`

- [ ] **Step 3: Implement**

Append to `assets/signals.py`:

```python
def compute_mvrv_zscore_expanding(df: pd.DataFrame, min_periods: int = 365) -> pd.Series:
    """Causal MVRV z-score: mean/std over an expanding window ending at each
    row, so the value on date t uses only data available on date t. The first
    min_periods-1 rows are NaN (scored neutral downstream). Values are NOT
    comparable to the full-history z-score early on — the expanding mean/std
    drift as history accumulates."""
    mvrv = df["mvrv"]
    mean = mvrv.expanding(min_periods=min_periods).mean()
    std = mvrv.expanding(min_periods=min_periods).std()
    z = (mvrv - mean) / std
    return z.replace([np.inf, -np.inf], np.nan)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_signals.py -v`
Expected: all PASS (including pre-existing tests — the module change is additive)

- [ ] **Step 5: Commit**

```bash
git add assets/signals.py tests/test_signals.py
git commit -m "feat(signals): causal expanding-window MVRV z-score (additive, unwired)"
```

---

### Task 4: Continuous signal scoring

Ternary 0/50/100 creates cliffs: 200W-MA at 1.005x scores 50, at 0.999x scores
100 — an ~8.6-point composite jump for a 0.6% price move. Replace with
piecewise-linear interpolation between the SAME calibrated thresholds. Additive
function; production `score_series` untouched in Phase A.

**Files:**
- Modify: `scripts/compute_signals.py` (append two functions)
- Modify: `tests/test_compute_signals.py` (append tests)

**Interfaces:**
- Produces: `continuous_score(value: float, invest_thresh: float, avoid_thresh: float) -> float` and `continuous_score_series(series: pd.Series, invest_thresh: float, avoid_thresh: float) -> pd.Series`; consumed by the harness (Task 6) and later Phase B. Contract: returns exactly `100.0` iff `value <= invest_thresh` (so `compute_signal_stats`'s `== 100` buy-fire logic keeps working unchanged), exactly `0.0` iff `value >= avoid_thresh`, `50.0` for NaN (mirrors `score_series`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_compute_signals.py`:

```python
def test_continuous_score_boundaries_and_midpoint():
    from scripts.compute_signals import continuous_score
    assert continuous_score(-0.5, -0.5, 1.5) == 100.0   # at invest thresh
    assert continuous_score(-2.0, -0.5, 1.5) == 100.0   # beyond invest
    assert continuous_score(1.5, -0.5, 1.5) == 0.0      # at avoid thresh
    assert continuous_score(3.0, -0.5, 1.5) == 0.0      # beyond avoid
    assert continuous_score(0.5, -0.5, 1.5) == 50.0     # exact midpoint


def test_continuous_score_is_monotone_decreasing():
    from scripts.compute_signals import continuous_score
    values = [continuous_score(v, 1.0, 1.2) for v in (1.0, 1.05, 1.1, 1.15, 1.2)]
    assert values == sorted(values, reverse=True)
    assert values[0] == 100.0 and values[-1] == 0.0


def test_continuous_score_nan_is_neutral():
    from scripts.compute_signals import continuous_score
    assert continuous_score(float("nan"), 1.0, 1.2) == 50.0


def test_continuous_score_requires_ordered_thresholds():
    from scripts.compute_signals import continuous_score
    import pytest
    with pytest.raises(AssertionError):
        continuous_score(0.5, 1.2, 1.0)  # invest must be < avoid
```

(Match the file's existing import style — if it imports as `from compute_signals import ...` with a sys.path insert, use that form instead.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_compute_signals.py -k continuous -v`
Expected: 4 FAIL with ImportError

- [ ] **Step 3: Implement**

Append to `scripts/compute_signals.py`:

```python
def continuous_score(value: float, invest_thresh: float, avoid_thresh: float) -> float:
    """Piecewise-linear 0-100 score between the same calibrated thresholds the
    ternary scorer uses: exactly 100.0 at/below invest_thresh, exactly 0.0
    at/above avoid_thresh, linear in between, 50.0 for NaN. Exactness at the
    ends matters: compute_signal_stats treats score == 100 as a buy-fire.
    Assumes higher raw value = worse (true of every current SignalSpec)."""
    assert invest_thresh < avoid_thresh, "invest_thresh must be below avoid_thresh"
    if pd.isna(value):
        return 50.0
    if value <= invest_thresh:
        return 100.0
    if value >= avoid_thresh:
        return 0.0
    return round(100.0 * (avoid_thresh - value) / (avoid_thresh - invest_thresh), 2)


def continuous_score_series(series: pd.Series, invest_thresh: float,
                            avoid_thresh: float) -> pd.Series:
    return series.apply(lambda v: continuous_score(v, invest_thresh, avoid_thresh))
```

- [ ] **Step 4: Run the whole test file**

Run: `python -m pytest tests/test_compute_signals.py -v`
Expected: all PASS (pre-existing ternary tests untouched)

- [ ] **Step 5: Commit**

```bash
git add scripts/compute_signals.py tests/test_compute_signals.py
git commit -m "feat(scoring): continuous piecewise-linear signal score (additive, unwired)"
```

---

### Task 5: Family-equal weights variant

Five of six signals are transforms of price-vs-its-own-history; precision
weighting lets near-duplicates vote independently AND rewards signals with
precision 1.0 on a handful of days. The robustness alternative: one equal vote
per signal FAMILY, split equally inside the family. Deliberately parameter-free.

**Files:**
- Modify: `scripts/experiment.py` (add `FAMILIES`, `family_equal_weights`)
- Modify: `tests/test_experiment.py` (add test)

**Interfaces:**
- Produces: `FAMILIES: dict[str, list[str]]`, `family_equal_weights(signal_names: list[str]) -> dict[str, float]` — usable as the `weight_fn` argument of `walk_forward_fixed`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experiment.py`:

```python
def test_family_equal_weights_sum_to_one_and_split_within_family():
    from experiment import FAMILIES, family_equal_weights
    names = [m for members in FAMILIES.values() for m in members]
    w = family_equal_weights(names)
    assert set(w) == set(names)
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)
    # 4 families -> each family totals 0.25; trend has 3 members
    assert w["mvrv_zscore"] == pytest.approx(0.25, abs=1e-3)
    assert w["ma_200w"] == pytest.approx(0.25 / 3, abs=1e-3)
    assert w["puell"] == pytest.approx(0.25, abs=1e-3)
    assert w["fear_greed"] == pytest.approx(0.25, abs=1e-3)


def test_family_equal_weights_rejects_unknown_signal():
    from experiment import family_equal_weights
    with pytest.raises(AssertionError):
        family_equal_weights(["mvrv_zscore", "not_a_signal"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment.py -k family -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement**

Add to `scripts/experiment.py`:

```python
FAMILIES = {
    "valuation": ["mvrv_zscore"],
    "trend":     ["ma_200w", "pi_cycle", "monthly_rsi"],
    "miners":    ["puell"],
    "sentiment": ["fear_greed"],
}


def family_equal_weights(signal_names: list) -> dict:
    """Equal weight per family, equal split within each family. Parameter-free
    by design — the robustness variant, not the clever one."""
    known = {m for members in FAMILIES.values() for m in members}
    assert set(signal_names) == known, f"signals/FAMILIES mismatch: {set(signal_names) ^ known}"
    w = {}
    fam_w = 1.0 / len(FAMILIES)
    for members in FAMILIES.values():
        for m in members:
            w[m] = round(fam_w / len(members), 4)
    return w
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_experiment.py -k family -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/experiment.py tests/test_experiment.py
git commit -m "feat(experiment): family-equal weight variant"
```

---

### Task 6: Variant grid runner + report on real BTC history

Wire everything into a staged grid, run it on `data/bitcoin_history.csv`, and
emit machine-readable + human-readable reports. The decision rule is fixed
BEFORE looking at results (it is pre-registered here); Task 7 only applies it.

**Files:**
- Modify: `scripts/experiment.py` (add `build_signal_history`, `run_variant`, rewrite `main`)
- Modify: `tests/test_experiment.py` (add build test)
- Output: `data/experiments/bitcoin_model_fixes.json`, `data/experiments/bitcoin_model_fixes_report.md`

**Interfaces:**
- Consumes: everything from Tasks 1-5, `compute_signals.score_series`, `compute_signals.continuous_score_series`, `assets.signals.compute_mvrv_zscore_expanding`
- Produces: `build_signal_history(price_df, specs, causal_z: bool, continuous: bool) -> pd.DataFrame` (columns `date`, `{key}_raw`, `{key}` per spec), `run_variant(price_df, cfg, causal_z, continuous, family_weights) -> dict`

- [ ] **Step 1: Write the failing test for the history builder**

Append to `tests/test_experiment.py`:

```python
def test_build_signal_history_variant_flags():
    from experiment import build_signal_history
    from assets import bitcoin
    n = 2500
    dates = pd.date_range("2013-01-01", periods=n, freq="D")
    rng = np.random.default_rng(11)
    price = 100 * np.exp(np.arange(n) / 900)
    df = pd.DataFrame({
        "date": dates, "price": price,
        "market_cap": price * 1e7,
        "mvrv": rng.normal(2.0, 0.8, size=n),
        "miner_revenue": rng.uniform(1e6, 5e6, size=n),
        "fear_greed": rng.uniform(0, 100, size=n),
    })
    specs = bitcoin.CONFIG.signals

    ternary = build_signal_history(df, specs, causal_z=False, continuous=False)
    assert set(ternary["mvrv_zscore"].dropna().unique()) <= {0, 50, 100}

    cont = build_signal_history(df, specs, causal_z=False, continuous=True)
    mid = cont["mvrv_zscore"].dropna()
    assert ((0 <= mid) & (mid <= 100)).all()
    assert len(set(mid.unique()) - {0.0, 50.0, 100.0}) > 0  # actually interpolates

    causal = build_signal_history(df, specs, causal_z=True, continuous=False)
    # expanding z with min_periods=365: first 364 raws NaN -> neutral 50
    assert causal["mvrv_zscore_raw"].iloc[:364].isna().all()
    assert (causal["mvrv_zscore"].iloc[:364] == 50).all()
    # non-mvrv signals identical across the causal_z flag
    pd.testing.assert_series_equal(causal["ma_200w"], ternary["ma_200w"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiment.py::test_build_signal_history_variant_flags -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement builder, variant runner, and main**

Add to `scripts/experiment.py` (imports at top of file):

```python
from assets.signals import compute_mvrv_zscore_expanding
from compute_signals import score_series, continuous_score_series
```

Then:

```python
def build_signal_history(price_df, specs, causal_z: bool, continuous: bool) -> pd.DataFrame:
    """Rebuild the signal history from raw price/on-chain data under variant
    flags. Mirrors compute_signals.compute_all_signals but swaps the z-score
    compute and/or the scoring function. Sell columns are irrelevant here."""
    out = pd.DataFrame({"date": price_df["date"]})
    for spec in specs:
        compute = spec.compute
        if causal_z and spec.key == "mvrv_zscore":
            compute = lambda df: compute_mvrv_zscore_expanding(df, MIN_PERIODS_Z)
        raw = compute(price_df)
        out[f"{spec.key}_raw"] = raw
        if continuous:
            out[spec.key] = continuous_score_series(raw, spec.invest_thresh, spec.avoid_thresh)
        else:
            out[spec.key] = score_series(raw, spec.invest_thresh, spec.avoid_thresh)
    return out


def run_variant(price_df, cfg, causal_z: bool, continuous: bool, family_weights: bool) -> dict:
    signal_names = [s.key for s in cfg.signals]
    signals_df = build_signal_history(price_df, cfg.signals, causal_z, continuous)
    merged = price_df[["date", "price"]].merge(signals_df, on="date", how="inner").reset_index(drop=True)
    fwd = forward_returns(merged["price"])
    eval_good = _good_aligned_to(merged, price_df, cfg.good_entry(price_df))  # hindsight OK for eval
    weight_fn = family_equal_weights if family_weights else None
    oos = walk_forward_fixed(price_df, signals_df, cfg, signal_names, weight_fn=weight_fn)
    result = evaluate(oos, eval_good, fwd, merged["date"])
    result["flags"] = {"causal_z": causal_z, "continuous": continuous,
                       "family_weights": family_weights}
    return result


def zscore_threshold_diagnostics(price_df) -> dict:
    """Where do the calibrated z thresholds (-0.5 / 1.5) sit in each version's
    distribution? Large percentile drift means Phase B must revisit thresholds."""
    from assets.signals import compute_mvrv_zscore
    full = compute_mvrv_zscore(price_df).dropna()
    expanding = compute_mvrv_zscore_expanding(price_df, MIN_PERIODS_Z).dropna()
    def pct_below(s, x):
        return round(float((s < x).mean()), 4)
    return {
        "full_history": {"pct_below_invest(-0.5)": pct_below(full, -0.5),
                         "pct_above_avoid(1.5)": round(1 - pct_below(full, 1.5), 4)},
        "expanding":    {"pct_below_invest(-0.5)": pct_below(expanding, -0.5),
                         "pct_above_avoid(1.5)": round(1 - pct_below(expanding, 1.5), 4)},
    }


STAGES = [
    # (label, causal_z, continuous, family_weights)
    ("stage1_fixed_labels",        False, False, False),
    ("stage1c_causal_z",           True,  False, False),
    ("stage2_continuous",          True,  True,  False),
    ("stage2_family",              True,  False, True),
    ("stage2_continuous_family",   True,  True,  True),
]


def main():
    OUT_DIR.mkdir(exist_ok=True)
    cfg = bitcoin.CONFIG
    price_df, _ = load_btc()

    stored = json.loads((DATA_DIR / "bitcoin_validation.json").read_text())["out_of_sample"]
    parity = run_legacy_parity()
    match = (parity["timing_edge"]["edge"] == stored["timing_edge"]["edge"]
             and parity["invest_precision"]["precision"] == stored["invest_precision"]["precision"])
    print(f"legacy parity: edge={parity['timing_edge']['edge']} "
          f"(stored {stored['timing_edge']['edge']}) -> {'PASS' if match else 'FAIL'}")
    if not match:
        sys.exit(1)

    results = {"legacy_parity": parity,
               "zscore_threshold_diagnostics": zscore_threshold_diagnostics(price_df),
               "runs": {}}
    for label, cz, cont, fam in STAGES:
        print(f"running {label} ...")
        results["runs"][label] = run_variant(price_df, cfg, cz, cont, fam)
        e10 = results["runs"][label]["edge_at_coverage"]["0.1"]["edge"]
        ic = results["runs"][label]["spearman_ic"]
        print(f"  edge@10%={e10}  IC={ic}")

    (OUT_DIR / "bitcoin_model_fixes.json").write_text(json.dumps(results, indent=2))

    lines = ["# BTC model-fixes experiment — OOS comparison", "",
             "| run | edge@5% | edge@10% | precision@10% | IC | scored days |",
             "|---|---|---|---|---|---|"]
    for label, r in results["runs"].items():
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            label,
            r["edge_at_coverage"]["0.05"]["edge"],
            r["edge_at_coverage"]["0.1"]["edge"],
            r["precision_at_coverage"]["0.1"]["precision"],
            r["spearman_ic"],
            r["scored_days"]))
    lines += ["", "## Per-cycle edge@10%", ""]
    for label, r in results["runs"].items():
        cycles = {c: v["edge"] for c, v in r["edge_by_cycle_10pct"].items()}
        lines.append(f"- **{label}**: {cycles}")
    (OUT_DIR / "bitcoin_model_fixes_report.md").write_text("\n".join(lines))
    print(f"report written to {OUT_DIR / 'bitcoin_model_fixes_report.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the unit test, then the full grid on real data**

Run: `python -m pytest tests/test_experiment.py -v`
Expected: all PASS

Run: `python scripts/experiment.py`
Expected: parity PASS line, five `running stage...` lines each with an edge@10% and IC, both output files created. Runtime: minutes (5 walk-forwards, each recomputing labels ~40 times over ~5,800 rows).

- [ ] **Step 5: Commit (including the generated report — it is the evidence)**

```bash
git add scripts/experiment.py tests/test_experiment.py data/experiments/
git commit -m "feat(experiment): staged variant grid + OOS comparison report on BTC history"
```

---

### Task 7: Decision write-up against the pre-registered rule — USER CHECKPOINT

**Files:**
- Create: `docs/superpowers/specs/2026-07-01-btc-model-fixes-decision.md`

**The pre-registered rule (fixed now, applied verbatim then):**

1. **Correctness fixes are adopted unconditionally**: leak-fixed labels and causal z-score are bug fixes, not optimizations. Their run (`stage1c_causal_z`) becomes the *honest baseline* — even if its metrics are worse than legacy, worse-but-true beats better-but-leaky.
2. **`continuous` is adopted** iff, vs `stage1c_causal_z`: edge@10% is ≥, AND IC drops by < 0.02, AND precision@10%-coverage drops by < 0.05. (Coverage-matched metrics only — a fixed composite cutoff like ≥60 selects different day counts under ternary vs continuous scoring and cannot compare them fairly.)
3. **`family_weights` is adopted** by the same rule. If both pass individually, `stage2_continuous_family` must also be ≥ `stage1c_causal_z` on edge@10%, else adopt only the single better one.
4. **Robustness check**: an adopted improvement must have edge@10% > 0 in at least 2 of the halving cycles that have scored OOS days. A variant that only worked in one era is rejected.
5. **Kill criterion**: if `stage1c_causal_z` AND every stage2 run have edge@10% ≤ 0, the conclusion is "no demonstrated timing edge once leaks are removed" — Phase B then descopes to: ship the correctness fixes, reframe the dashboard as descriptive (not predictive), and do NOT add new signals to chase a positive number.

- [ ] **Step 1: Write the decision doc**

Fill `docs/superpowers/specs/2026-07-01-btc-model-fixes-decision.md` with: the comparison table copied from the report, the rule-by-rule verdict (cite numbers), the z-threshold diagnostic and whether Phase B needs threshold recalibration, and the recommended Phase B scope.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-01-btc-model-fixes-decision.md
git commit -m "docs: model-fixes decision per pre-registered rule"
```

- [ ] **Step 3: STOP — present the decision doc to the user**

Do not start Phase B (production wiring: `compute_all_signals`, `score.py` status logic, `validate_composite.py` port of the leak fix, threshold recalibration if needed, ETH's `eth_btc_ratio_z` look-ahead, locked-formula test updates, data regeneration). Phase B gets its own brainstorm + plan informed by the decision doc.

---

## Known limitations (accepted, not fixable by this plan)

- **One history, few cycles.** BTC has ~3-4 exploitable cycles; every metric here has effective n in the single digits. The per-cycle breakdown exposes this; nothing cures it.
- **Overlapping forward windows.** 548-day forward returns sampled every 90 days are heavily autocorrelated; no significance tests are attempted because none would be honest.
- **Residual multiple-comparison risk.** Five pre-registered runs on one OOS series still burn that series a little. Mitigated by pre-registration and the simplicity-first rule; not eliminated.
- **The label definition itself is untested.** `good_entry` hard-codes the halving-cycle thesis (dates through 2030). If the cycle regime is dead, tuning against these labels inherits the error. Out of scope here; flagged for Phase B discussion.
- **`min_periods=365` and family groupings are judgment calls,** pre-registered to avoid tuning, not derived from data.
