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
